from __future__ import annotations

from dataclasses import replace
import time
import numpy as np


class QualityFunnel:
    """Sequential V1.1 quality filters; expensive work is short-circuited."""

    def __init__(self, config, evaluator):
        self.config, self.evaluator = config, evaluator
        self._neighbor_cache = {}
        self.stats = {"plateau_evaluations": 0, "plateau_cache_hits": 0, "plateau_early_exits": 0, "cost_evaluations": 0, "execution_evaluations": 0}

    def _basic(self, result):
        cfg = self.config.get("funnel.basic", {})
        reasons = []
        if result.trade_count < int(cfg.get("min_trades", 20)): reasons.append("LOW_TRADE_COUNT")
        if result.profit_factor < float(cfg.get("min_pf", .95)): reasons.append("LOW_PROFIT_FACTOR")
        if result.expectancy < float(cfg.get("min_expectancy", -float("inf"))): reasons.append("NEGATIVE_EXPECTANCY")
        if result.sharpe < float(cfg.get("min_sharpe", -float("inf"))): reasons.append("LOW_SHARPE")
        if result.max_drawdown > float(cfg.get("max_drawdown", .5)): reasons.append("EXCESSIVE_DRAWDOWN")
        return not reasons, reasons

    def basic_check(self, result):
        return self._basic(result)

    def _stability(self, strategy):
        cfg = self.config.get("funnel.stability", {})
        if not cfg.get("enabled", True): return True, 1.0, [], []
        nseg, minimum = max(2, int(cfg.get("segments", 4))), int(cfg.get("min_trades_per_segment", 20))
        n, rows = len(self.evaluator.data), []
        for i in range(nseg):
            lo, hi = i * n // nseg, (i + 1) * n // nseg
            r = self.evaluator.evaluate(strategy, start=lo, end=hi, rich=False)
            rows.append({"trades": r.trade_count, "pf": r.profit_factor, "expectancy": r.expectancy, "max_drawdown": r.max_drawdown})
        min_pf = float(cfg.get("min_pf", self.config.get("funnel.basic.min_pf", .95)))
        positive = sum(x["trades"] >= minimum and x["expectancy"] > 0 and x["pf"] >= min_pf for x in rows)
        score = positive / nseg
        passed = positive >= int(cfg.get("min_positive_segments", max(1, nseg - 1))) and all(x["trades"] >= minimum for x in rows)
        reason = [] if passed else (["INSUFFICIENT_SEGMENT_TRADES"] if any(x["trades"] < minimum for x in rows) else ["UNSTABLE_OVER_TIME"])
        return passed, score, reason, rows

    def _plateau(self, strategy):
        cfg = self.config.get("funnel.plateau", {})
        if not cfg.get("enabled", True): return True, 1.0, [], {}
        values = []; seen = set(); baseline_pf = float(self.config.get("funnel.basic.min_pf", .95))
        for field in ("stop_atr", "target_atr", "time_exit"):
            base = getattr(strategy, field)
            for mult in (-.2, -.1, .1, .2):
                value = max(.25, round(base * (1 + mult), 6)) if field != "time_exit" else max(1, int(round(base * (1 + mult))))
                key = (strategy.canonical_hash, field, value)
                neighbor = replace(strategy, **{field: value})
                if neighbor.canonical_hash in seen: continue
                seen.add(neighbor.canonical_hash)
                if key not in self._neighbor_cache:
                    self._neighbor_cache[key] = self.evaluator.evaluate(neighbor, rich=False); self.stats["plateau_evaluations"] += 1
                else:
                    self.stats["plateau_cache_hits"] += 1
                values.append(self._neighbor_cache[key])
        min_pf = float(self.config.get("funnel.basic.min_pf", .95))
        passed = [r for r in values if r.trade_count and r.profit_factor >= min_pf and r.expectancy >= 0]
        score = len(passed) / max(1, len(values)); threshold = float(cfg.get("min_pass_ratio", .35))
        meta = {"neighbors_tested": len(values), "neighbors_passed": len(passed), "worst_neighbor": min((r.profit_factor for r in values), default=0.0), "median_neighbor": float(np.median([r.profit_factor for r in values])) if values else 0.0}
        relative_median = meta["median_neighbor"] >= max(min_pf, baseline_pf * .90)
        return score >= threshold and relative_median, score, ([] if score >= threshold and relative_median else ["NARROW_PARAMETER_PEAK"]), meta

    def _cost(self, strategy):
        cfg = self.config.get("funnel.cost_stress", {})
        if not cfg.get("enabled", True): return True, 1.0, [], {}
        mults = cfg.get("multipliers", [1.25, 1.5, 2.0]); rows = []
        for m in mults:
            rows.append(self.evaluator.evaluate(strategy, cost_multiplier=float(m), rich=False)); self.stats["cost_evaluations"] += 1
        passed = [r for r in rows if r.profit_factor >= float(cfg.get("min_pf", .90)) and r.expectancy >= float(cfg.get("min_expectancy", -float("inf")))]
        score = len(passed) / max(1, len(rows)); threshold = float(cfg.get("min_pass_ratio", .67))
        return score >= threshold, score, ([] if score >= threshold else ["COST_FRAGILE"]), {"multipliers": list(mults), "metrics": [{"pf": r.profit_factor, "expectancy": r.expectancy} for r in rows]}

    def _execution(self, strategy):
        cfg = self.config.get("funnel.execution_stress", {})
        if not cfg.get("enabled", True): return True, 1.0, [], {}
        delays = cfg.get("delays", [1, 2]); rows = []
        for d in delays:
            rows.append(self.evaluator.evaluate(strategy, entry_delay=int(d), rich=False)); self.stats["execution_evaluations"] += 1
        passed = [r for r in rows if r.trade_count and r.expectancy >= float(cfg.get("min_expectancy", -float("inf")))]
        score = len(passed) / max(1, len(rows)); threshold = float(cfg.get("min_pass_ratio", .5))
        return score >= threshold, score, ([] if score >= threshold else ["EXECUTION_FRAGILE"]), {"delays": list(delays), "metrics": [{"pf": r.profit_factor, "expectancy": r.expectancy} for r in rows]}

    def evaluate(self, strategy, result):
        stages = {"basic": False, "stability": False, "plateau": False, "cost_stress": False, "execution_stress": False, "diversity": False}
        passed, reasons = self._basic(result)
        if not passed: return self._out(stages, reasons)
        stages["basic"] = True
        stable, stability_score, reasons, segments = self._stability(strategy)
        if not stable: return self._out(stages, reasons, stability_score=stability_score, segments=segments)
        stages["stability"] = True
        plateau, plateau_score, reasons, plateau_meta = self._plateau(strategy)
        if not plateau: return self._out(stages, reasons, stability_score=stability_score, segments=segments, plateau_score=plateau_score, plateau_meta=plateau_meta)
        stages["plateau"] = True
        cost, cost_score, reasons, cost_meta = self._cost(strategy)
        if not cost: return self._out(stages, reasons, stability_score=stability_score, segments=segments, plateau_score=plateau_score, plateau_meta=plateau_meta, cost_score=cost_score, cost_meta=cost_meta)
        stages["cost_stress"] = True
        execution, execution_score, reasons, execution_meta = self._execution(strategy)
        if not execution: return self._out(stages, reasons, stability_score=stability_score, segments=segments, plateau_score=plateau_score, plateau_meta=plateau_meta, cost_score=cost_score, cost_meta=cost_meta, execution_score=execution_score, execution_meta=execution_meta)
        stages["execution_stress"] = True
        quality = float(np.clip(.4 * min(result.expectancy_r / .1, 1) + .15 * min(result.sharpe / 2, 1) + .15 * max(0, 1 - result.max_drawdown) + .1 * stability_score + .1 * plateau_score + .05 * cost_score + .05 * execution_score, 0, 1))
        return self._out(stages, [], stability_score=stability_score, segments=segments, plateau_score=plateau_score, plateau_meta=plateau_meta, cost_score=cost_score, cost_meta=cost_meta, execution_score=execution_score, execution_meta=execution_meta, quality_score=quality)

    def _out(self, stages, reasons, **extra):
        return {"passed": all(value for key, value in stages.items() if key != "diversity"), "reasons": reasons, "stages": stages, "stability_score": extra.get("stability_score", 0.0), "plateau_score": extra.get("plateau_score", 0.0), "cost_score": extra.get("cost_score", 0.0), "execution_score": extra.get("execution_score", 0.0), "monte_carlo_score": 0.0, "quality_score": extra.get("quality_score", 0.0), **extra}
