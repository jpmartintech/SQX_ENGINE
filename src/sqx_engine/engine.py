from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import numpy as np

from .config import EngineConfig
from .data import load_ohlcv
from .features import prepare_features
from .generators import GeneticGenerator, RandomGenerator
from .backtest import FastEvaluator
from .funnel import QualityFunnel
from .store import StrategyStore
from .portfolio import PortfolioBuilder


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
        ea = {str(t["entry_time"]) for t in a["result"].trades}
        eb = {str(t["entry_time"]) for t in b["result"].trades}
        overlap = len(ea & eb) / max(1, min(len(ea), len(eb)))
        return corr >= max_corr or overlap >= max_overlap

    def run(self):
        started = time.perf_counter()
        run_id = str(uuid.uuid4())
        timings = {}
        t = time.perf_counter(); data = load_ohlcv(self.config.get("data_path")); timings["data_loading"] = time.perf_counter() - t
        t = time.perf_counter(); features = prepare_features(data); timings["feature_calculation"] = time.perf_counter() - t
        evaluator = FastEvaluator(data, features, self.config.get("backtest.initial_capital", 10000), self.config.get("backtest.spread", 0.0), self.config.get("backtest.slippage", 0.0))
        generator_cls = GeneticGenerator if self.config.get("generator.type", "random") == "genetic" else RandomGenerator
        gen = generator_cls(self.config.get("market", "EURUSD"), self.config.get("timeframe", "H1"), self.config.get("generator.seed", 101), self.config.get("strategy.max_predicates", 2), population_size=self.config.get("generator.population_size", 40), mutation_rate=self.config.get("generator.mutation_rate", .35), crossover_rate=self.config.get("generator.crossover_rate", .70)) if generator_cls is GeneticGenerator else generator_cls(self.config.get("market", "EURUSD"), self.config.get("timeframe", "H1"), self.config.get("generator.seed", 101), self.config.get("strategy.max_predicates", 2))
        funnel = QualityFunnel(self.config, evaluator)
        store = StrategyStore(self.config.get("store.path", "runs/sqx_engine.sqlite"))
        requested = int(self.config.get("generator.evaluations", 100))
        store.start_run((run_id, None, None, self.config.get("market"), self.config.get("timeframe"), self.config.get("generator.type", "random"), self.config.get("generator.seed"), requested, 0, 0, 0, 0.0, self.config.config_hash, "RUNNING"))
        seen, records, basic_records, rejected = set(), [], [], 0
        rejection_counts = {}
        counters = {"generated": 0, "unique": 0, "backtested": 0, "basic_pass": 0, "stability_pass": 0, "plateau_pass": 0, "cost_pass": 0, "execution_pass": 0, "before_diversity": 0, "diversity_pass": 0}
        t_search = time.perf_counter()
        attempts = 0
        while len(seen) < requested and attempts < requested * 20:
            attempts += 1; strategy = gen.ask(); counters["generated"] += 1
            if strategy.canonical_hash in seen: continue
            seen.add(strategy.canonical_hash); counters["unique"] += 1
            t_eval = time.perf_counter(); result = evaluator.evaluate(strategy, rich=False); timings["fast_backtesting"] = timings.get("fast_backtesting", 0.0) + time.perf_counter() - t_eval; counters["backtested"] += 1
            basic_ok, basic_reasons = funnel.basic_check(result)
            if not basic_ok:
                f = {"passed": False, "reasons": basic_reasons, "stages": {"basic": False, "stability": False, "plateau": False, "cost_stress": False, "execution_stress": False, "diversity": False}, "quality_score": 0.0}
                store.add_strategy(strategy, result, f, self.config.get("generator.seed"), "REJECTED", run_id); rejected += 1
                for reason in basic_reasons: rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                gen.tell(strategy, result); continue
            counters["basic_pass"] += 1; basic_records.append((strategy, result)); gen.tell(strategy, result)
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
        for strategy, aggregate_result in advanced:
            result = evaluator.evaluate(strategy, rich=True)
            f = funnel.evaluate(strategy, result)
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
        checkpoint = {"run_id": run_id, "status": "COMPLETE", "evaluations": counters["unique"], "canonical_hashes": sorted(seen), "generator": getattr(gen, "state", lambda: {})(), "counters": counters}
        checkpoint_path = Path(self.config.get("checkpoint.path", f"runs/checkpoints/{run_id}.json")); checkpoint_path.parent.mkdir(parents=True, exist_ok=True); checkpoint_path.write_text(json.dumps(checkpoint, default=str, indent=2))
        top = store.top_strategies(self.config.get("market"), self.config.get("timeframe"), 10)
        database = {"runs": store.count("runs"), "strategies": store.count("strategies"), "funnel": store.count("funnel"), "candidates": len(final)}
        result = {"run_id": run_id, "market": self.config.get("market"), "timeframe": self.config.get("timeframe"), "requested": requested, "generated": counters["generated"], "unique": counters["unique"], "backtested": counters["backtested"], "basic_pass": counters["basic_pass"], "rejected": rejected, "rejection_reasons": rejection_counts, "counters": counters, "candidate_pool": len(advanced), "candidates": len(final), "portfolio_eligible": len(final), "portfolio_selected": len(portfolio["strategies"]), "runtime": elapsed, "strategies_per_sec": counters["backtested"] / elapsed, "strategies_per_hour": counters["backtested"] / elapsed * 3600, "final_candidates_per_hour": len(final) / elapsed * 3600, "timings": timings, "database": database, "portfolio": {"strategy_ids": [x["result"].strategy_id for x in portfolio["strategies"]], "weights": portfolio["weights"], "average_correlation": portfolio["average_correlation"], "max_correlation": portfolio["max_correlation"]}, "top_candidates": top, "checkpoint": str(checkpoint_path)}
        store.close(); return result
