from __future__ import annotations

import json
import time
import uuid
import signal
import os
from pathlib import Path

import numpy as np

from .config import EngineConfig
from .data.split import discovery_data
from .features import prepare_features
from .generators import GeneticGenerator, RandomGenerator
from .backtest import FastEvaluator, ParallelEvaluator, resolve_workers
from .funnel import QualityFunnel
from .store import StrategyStore
from .portfolio import PortfolioBuilder
from .runtime import CheckpointManager
from .backtest import EvaluationResult
from .strategy import StrategyDefinition

def _rss_mb():
    try:
        return int(Path('/proc/self/status').read_text().split('VmRSS:')[1].split()[0]) / 1024.0
    except (OSError, IndexError, ValueError):
        return 0.0


def _result_state(result):
    return {"strategy_id": result.strategy_id, "canonical_hash": result.canonical_hash, "trade_count": result.trade_count, "net_profit": result.net_profit, "return_pct": result.return_pct, "profit_factor": result.profit_factor, "expectancy": result.expectancy, "expectancy_r": result.expectancy_r, "sharpe": result.sharpe, "max_drawdown": result.max_drawdown, "win_rate": result.win_rate, "average_trade": result.average_trade, "long_trades": result.long_trades, "short_trades": result.short_trades}


def _result_from_state(raw):
    return EvaluationResult(**raw, trade_returns=[], equity_curve=[], trades=[])


class StrategyFactory:
    def __init__(self, config: EngineConfig):
        self.config = config

    @staticmethod
    def _similar(a, b, max_corr, max_overlap):
        x, y = np.asarray(a["result"].trade_returns, float), np.asarray(b["result"].trade_returns, float)
        n = max(len(x), len(y))
        if n < 2: corr = 0.0
        else:
            x, y = np.pad(x, (0, n - len(x))), np.pad(y, (0, n - len(y)))
            corr = 0.0 if not np.std(x) or not np.std(y) else abs(float(np.corrcoef(x, y)[0, 1]))
        if corr >= max_corr: return True
        # Correlation below this level is already behaviorally different; only
        # compute the more expensive timestamp overlap in the ambiguous band.
        if corr < max_corr * .60: return False
        ea = {str(t["entry_time"]) for t in a["result"].trades}
        eb = {str(t["entry_time"]) for t in b["result"].trades}
        overlap = len(ea & eb) / max(1, min(len(ea), len(eb)))
        return overlap >= max_overlap

    def run(self, resume=False, workers=None):
        started = time.perf_counter()
        run_id = str(uuid.uuid4())
        timings = {}
        t = time.perf_counter(); data, discovery_provenance = discovery_data(self.config); timings["data_loading"] = time.perf_counter() - t
        t = time.perf_counter(); features = prepare_features(data); timings["feature_calculation"] = time.perf_counter() - t
        cache_size = int(self.config.get("execution.cache_size", 4096))
        engine_name = self.config.get("engine", "auto")
        initial_capital = self.config.get("backtest.initial_capital", 10000)
        spread = self.config.get("backtest.spread", 0.0)
        slippage = self.config.get("backtest.slippage", 0.0)
        evaluator = FastEvaluator(data, features, initial_capital, spread, slippage, cache_size=cache_size, engine=engine_name)
        requested_workers = workers if workers is not None else self.config.get("execution.workers", 1)
        workers_used = resolve_workers(requested_workers, self.config.get("execution.reserved_cores", 1))
        batch_size = max(1, int(self.config.get("execution.batch_size", max(8, workers_used * 4))))
        parallel = ParallelEvaluator(data, features, initial_capital, spread, slippage, workers_used, cache_size=cache_size, engine=engine_name) if workers_used > 1 else None
        generator_cls = GeneticGenerator if self.config.get("generator.type", "random") == "genetic" else RandomGenerator
        gen = generator_cls(self.config.get("market", "EURUSD"), self.config.get("timeframe", "H1"), self.config.get("generator.seed", 101), self.config.get("strategy.max_predicates", 2), population_size=self.config.get("generator.population_size", 40), mutation_rate=self.config.get("generator.mutation_rate", .35), crossover_rate=self.config.get("generator.crossover_rate", .70), mode=self.config.get("generator.mode", "legacy"), novelty_retry_limit=self.config.get("generator.novelty.retry_limit", 8)) if generator_cls is GeneticGenerator else generator_cls(self.config.get("market", "EURUSD"), self.config.get("timeframe", "H1"), self.config.get("generator.seed", 101), self.config.get("strategy.max_predicates", 2))
        funnel = QualityFunnel(self.config, evaluator)
        store = StrategyStore(self.config.resolve_path("store.path", "runs/sqx_engine.sqlite"))
        requested = int(self.config.get("generator.evaluations", 100))
        checkpoint_path = self.config.resolve_path("checkpoint.path", f"runs/checkpoints/{run_id}.json"); checkpoint = CheckpointManager(checkpoint_path, context=discovery_provenance)
        resume_state = checkpoint.load() if (resume or self.config.get("runtime.resume", False)) else None
        if resume_state and resume_state.get("status") == "COMPLETE" and resume_state.get("result") is not None:
            # A completed checkpoint is an immutable run result, not a second
            # request to replay the funnel (which would duplicate rejection
            # counts and store rows).  This makes --resume idempotent.
            if parallel is not None:
                parallel.shutdown()
            store.close()
            return resume_state["result"]
        if resume_state and resume_state.get("status") in {"RUNNING", "INTERRUPTED", "COMPLETE"}:
            run_id = resume_state["run_id"]
            if hasattr(gen, "set_state"): gen.set_state(resume_state.get("generator", {}))
            seen = set(resume_state.get("canonical_hashes", [])); basic_records = [(StrategyDefinition.from_json(x["strategy"]), _result_from_state(x["result"])) for x in resume_state.get("basic_records", [])]
            counters = resume_state.get("counters", {"generated": 0, "attempts": 0, "duplicates": 0, "unique": len(seen), "backtested": len(seen), "basic_pass": len(basic_records), "stability_pass": 0, "plateau_pass": 0, "cost_pass": 0, "execution_pass": 0, "before_diversity": 0, "diversity_pass": 0})
            rejected = int(resume_state.get("rejected", 0)); rejection_counts = resume_state.get("rejection_counts", {})
        else:
            if discovery_provenance is not None and store.count("runs"):
                if parallel is not None: parallel.shutdown()
                store.close()
                raise ValueError("Clean discovery requires an empty database or a matching checkpoint resume")
            store.start_run((run_id, None, None, self.config.get("market"), self.config.get("timeframe"), self.config.get("generator.type", "random"), self.config.get("generator.seed"), requested, 0, 0, 0, 0.0, self.config.config_hash, "RUNNING"))
            seen, basic_records, rejected, counters, rejection_counts = set(), [], 0, {"generated": 0, "attempts": 0, "duplicates": 0, "unique": 0, "backtested": 0, "basic_pass": 0, "stability_pass": 0, "plateau_pass": 0, "cost_pass": 0, "execution_pass": 0, "before_diversity": 0, "diversity_pass": 0}, {}
        if discovery_provenance is not None:
            store.db.execute('CREATE TABLE IF NOT EXISTS discovery_provenance (run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL)')
            other_runs = store.db.execute('SELECT COUNT(*) FROM runs WHERE run_id != ?', (run_id,)).fetchone()[0]
            if other_runs:
                raise ValueError('Clean discovery requires a dedicated database per run')
            store.db.execute('INSERT OR REPLACE INTO discovery_provenance VALUES (?,?)', (run_id, json.dumps(discovery_provenance, sort_keys=True)))
            store.commit()
        records = []
        t_search = time.perf_counter()
        attempts = int(counters.get("attempts", counters.get("generated", 0)))
        duplicates = int(counters.get("duplicates", 0))
        interrupted = False
        stop_requested = False
        def _sigint(_signum, _frame):
            nonlocal stop_requested
            stop_requested = True
        previous_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, _sigint)
        checkpoint_every = int(self.config.get("runtime.checkpoint_every_evaluations", 500))
        next_checkpoint = ((len(seen) // checkpoint_every) + 1) * checkpoint_every if checkpoint_every else 0
        heartbeat_seconds = float(self.config.get("runtime.heartbeat_seconds", 60.0))
        next_heartbeat = time.perf_counter() + heartbeat_seconds
        while len(seen) < requested and attempts < requested * 20 and not stop_requested:
            attempts += 1; counters["attempts"] = attempts; strategy = gen.ask(known_hashes=seen); counters["generated"] += 1
            if strategy.canonical_hash in seen:
                duplicates += 1; counters["duplicates"] = duplicates
                continue
            seen.add(strategy.canonical_hash); counters["unique"] += 1
            t_eval = time.perf_counter()
            # Genetic feedback remains ask -> evaluate -> tell. This preserves
            # V1.2 semantics; parallel workers are used for independent later
            # evaluations rather than changing the evolutionary trajectory.
            result = evaluator.evaluate(strategy, rich=False)
            timings["fast_backtesting"] = timings.get("fast_backtesting", 0.0) + time.perf_counter() - t_eval
            counters["backtested"] += 1
            basic_ok, basic_reasons = funnel.basic_check(result)
            if not basic_ok:
                f = {"passed": False, "reasons": basic_reasons, "stages": {"basic": False, "stability": False, "plateau": False, "cost_stress": False, "execution_stress": False, "diversity": False}, "quality_score": 0.0}
                store.add_strategy(strategy, result, f, self.config.get("generator.seed"), "REJECTED", run_id); rejected += 1
                for reason in basic_reasons: rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            else:
                counters["basic_pass"] += 1; basic_records.append((strategy, result))
            gen.tell(strategy, result)
            if checkpoint_every and len(seen) >= next_checkpoint:
                store.commit(); checkpoint.save({"run_id": run_id, "status": "RUNNING", "evaluations": len(seen), "canonical_hashes": sorted(seen), "generator": getattr(gen, "state", lambda: {})(), "counters": counters, "rejected": rejected, "rejection_counts": rejection_counts, "basic_records": [{"strategy": s.to_json(), "result": _result_state(r)} for s, r in basic_records]})
                next_checkpoint = ((len(seen) // checkpoint_every) + 1) * checkpoint_every
            now = time.perf_counter()
            if now >= next_heartbeat:
                elapsed_window = max(1e-9, now - t_search)
                print(f"SQX HEARTBEAT unique={len(seen)}/{requested} attempts={attempts} duplicates={duplicates} duplicate_rate={duplicates/max(1, attempts):.1%} unique/sec={len(seen)/elapsed_window:.2f} RSS={_rss_mb():.1f}MB", flush=True)
                next_heartbeat = now + heartbeat_seconds
        if stop_requested:
            interrupted = True
            store.commit()
            checkpoint.save({"run_id": run_id, "status": "INTERRUPTED", "evaluations": len(seen), "canonical_hashes": sorted(seen), "generator": getattr(gen, "state", lambda: {})(), "counters": counters, "rejected": rejected, "rejection_counts": rejection_counts, "basic_records": [{"strategy": s.to_json(), "result": _result_state(r)} for s, r in basic_records]})
            if parallel is not None: parallel.shutdown()
            store.close(); signal.signal(signal.SIGINT, previous_sigint)
            return {"run_id": run_id, "status": "INTERRUPTED", "requested": requested, "attempts": attempts, "duplicates": duplicates, "unique": len(seen), "backtested": counters["backtested"], "checkpoint": str(checkpoint_path)}
        timings["generation_and_basic"] = time.perf_counter() - t_search
        candidate_limit = int(self.config.get("candidate_pool.size", requested))
        basic_records.sort(key=lambda x: (x[1].expectancy_r, x[1].sharpe, -x[1].max_drawdown, x[0].canonical_hash), reverse=True)
        advanced = basic_records[:candidate_limit]
        advanced_hashes = {s.canonical_hash for s, _ in advanced}
        for strategy, result in basic_records[candidate_limit:]:
            f = {"passed": False, "reasons": ["CANDIDATE_POOL_LIMIT"], "stages": {"basic": True, "stability": False, "plateau": False, "cost_stress": False, "execution_stress": False, "diversity": False}, "quality_score": 0.0}
            store.add_strategy(strategy, result, f, self.config.get("generator.seed"), "BASIC_PASS", run_id)
            rejection_counts["CANDIDATE_POOL_LIMIT"] = rejection_counts.get("CANDIDATE_POOL_LIMIT", 0) + 1
            rejected += 1
        t_funnel = time.perf_counter()
        advanced_results = (evaluator.evaluate_batch([s for s, _ in advanced], rich=False)
                           if parallel is None else parallel.evaluate_batch([s for s, _ in advanced], rich=False))
        for (strategy, aggregate_result), aggregate in zip(advanced, advanced_results):
            f = funnel.evaluate(strategy, aggregate)
            result = evaluator.evaluate(strategy, rich=True) if f["passed"] else aggregate
            counters["stability_pass"] += int(f["stages"].get("stability", False)); counters["plateau_pass"] += int(f["stages"].get("plateau", False)); counters["cost_pass"] += int(f["stages"].get("cost_stress", False)); counters["execution_pass"] += int(f["stages"].get("execution_stress", False))
            if f["passed"]: records.append({"strategy": strategy, "result": result, "funnel": f}); counters["before_diversity"] += 1
            else:
                rejected += 1
                for reason in f.get("reasons", []): rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            store.add_strategy(strategy, result, f, self.config.get("generator.seed"), "CANDIDATE" if f["passed"] else "REJECTED", run_id)
        timings["quality_funnel"] = time.perf_counter() - t_funnel
        t_div = time.perf_counter(); final = []
        dcfg = self.config.get("funnel.diversity", {}); max_corr = float(dcfg.get("max_pnl_correlation", dcfg.get("max_correlation", .85))); max_overlap = float(dcfg.get("max_entry_overlap", .80))
        for item in sorted(records, key=lambda x: (x["funnel"].get("quality_score", 0), x["result"].expectancy_r), reverse=True):
            if any(self._similar(item, old, max_corr, max_overlap) for old in final):
                item["funnel"]["stages"]["diversity"] = False; item["funnel"]["reasons"] = ["BEHAVIORAL_CLONE"]; rejected += 1; rejection_counts["BEHAVIORAL_CLONE"] = rejection_counts.get("BEHAVIORAL_CLONE", 0) + 1
                store.add_strategy(item["strategy"], item["result"], item["funnel"], self.config.get("generator.seed"), "REJECTED", run_id)
                continue
            item["funnel"]["stages"]["diversity"] = True; final.append(item)
        counters["diversity_pass"], timings["diversity"] = len(final), time.perf_counter() - t_div
        for item in final:
            store.add_strategy(item["strategy"], item["result"], item["funnel"], self.config.get("generator.seed"), "CANDIDATE", run_id)
        store.commit()
        portfolio = PortfolioBuilder(self.config.get("portfolio.max_strategies", 10), self.config.get("portfolio.max_correlation", .70)).build(final)
        timings["portfolio"] = time.perf_counter() - t_div - timings["diversity"]
        elapsed = time.perf_counter() - started
        store.finish_run(run_id, (None, counters["generated"], counters["backtested"], len(final), elapsed, "COMPLETE"))
        top = store.top_strategies(self.config.get("market"), self.config.get("timeframe"), 10)
        database = {"runs": store.count("runs"), "strategies": store.count("strategies"), "funnel": store.count("funnel"), "candidates": len(final)}
        timings["generator_telemetry"] = getattr(gen, "telemetry", {})
        signal.signal(signal.SIGINT, previous_sigint)
        result = {"run_id": run_id, "market": self.config.get("market"), "timeframe": self.config.get("timeframe"), "requested": requested, "generated": counters["generated"], "attempts": counters.get("attempts", counters["generated"]), "duplicates": counters.get("duplicates", 0), "unique": counters["unique"], "backtested": counters["backtested"], "basic_pass": counters["basic_pass"], "rejected": rejected, "rejection_reasons": rejection_counts, "counters": counters, "candidate_pool": len(advanced), "candidates": len(final), "portfolio_eligible": len(final), "portfolio_selected": len(portfolio["strategies"]), "runtime": elapsed, "strategies_per_sec": counters["backtested"] / elapsed, "strategies_per_hour": counters["backtested"] / elapsed * 3600, "final_candidates_per_hour": len(final) / elapsed * 3600, "timings": timings, "memory_rss_mb": _rss_mb(), "database": database, "portfolio": {"strategy_ids": [x["result"].strategy_id for x in portfolio["strategies"]], "weights": portfolio["weights"], "average_correlation": portfolio["average_correlation"], "max_correlation": portfolio["max_correlation"], "combined_return": portfolio["combined_return"], "combined_sharpe": portfolio["combined_sharpe"], "combined_max_drawdown": portfolio["combined_max_drawdown"]}, "top_candidates": top, "checkpoint": str(checkpoint_path)}
        timings["cache"] = evaluator.cache_stats()
        result["workers_requested"] = requested_workers
        result["workers_used"] = workers_used
        result["batch_size"] = batch_size
        if parallel is not None:
            parallel.shutdown()
        checkpoint.save({"run_id": run_id, "status": "COMPLETE", "evaluations": counters["unique"], "canonical_hashes": sorted(seen), "generator": getattr(gen, "state", lambda: {})(), "counters": counters, "rejected": rejected, "rejection_counts": rejection_counts, "basic_records": [{"strategy": s.to_json(), "result": _result_state(r)} for s, r in basic_records], "result": result})
        store.close(); return result
