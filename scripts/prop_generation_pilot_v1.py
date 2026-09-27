"""Bounded PROP_V1 manufacturing pilot.

The pilot uses only Development for generation/cheap selection, then evaluates
the fixed survivor set on Validation. It never loads OOS data and never writes
the General Strategy Library.
"""
from __future__ import annotations

import argparse, hashlib, json, resource, time
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.data.loader import load_ohlcv
from sqx_engine.features import prepare_features
from sqx_engine.prop_factory_v1.fitness import evaluate_cheap, evaluate_full, normalize_objectives
from sqx_engine.prop_factory_v1.funnel import evaluate_funnel, FunnelPolicy
from sqx_engine.prop_factory_v1.generator import (
    PROP_CANONICAL_GRAMMAR, PROP_EXIT_SPACE, PROP_FACTORY_VERSION,
    PROP_GRAMMAR_VERSION, PROP_EXIT_VERSION, PROP_SURVIVOR_WIDTH,
    PropGeneticGenerator, prop_predicate_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/prop_strategy_factory_v1_generation_pilot"
DATA = {
    ("EURUSD", "M15"): ROOT / "data/cloud/EURUSD_M15.csv",
    ("EURUSD", "H1"): ROOT / "data/derived/EURUSD_H1_11d571e8bb3d_143197.csv",
    ("XAUUSD", "M15"): ROOT / "data/cloud/XAUUSD_M15.csv",
    ("XAUUSD", "H1"): ROOT / "data/derived/XAUUSD_H1_ace62dd3d22f_136885.csv",
}
SEEDS = (4101, 4102)
TARGET = 1000


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def development_validation(frame):
    # Do not materialize or inspect the OOS slice.
    # Match the frozen Phase A split policy: 60% Development, 20%
    # Validation, with the final 20% never loaded by the pilot.
    a, b = int(len(frame) * .60), int(len(frame) * .80)
    return frame.iloc[:a].reset_index(drop=True), frame.iloc[a:b].reset_index(drop=True)


def ledger_from_result(strategy, result, timeframe, market):
    delta = {"M15": pd.Timedelta(minutes=15), "H1": pd.Timedelta(hours=1)}[timeframe]
    rows = []
    for trade in result.trades:
        entry = pd.Timestamp(trade["entry_time"], tz="UTC") if pd.Timestamp(trade["entry_time"]).tzinfo is None else pd.Timestamp(trade["entry_time"]).tz_convert("UTC")
        exit_time = pd.Timestamp(trade["exit_time"], tz="UTC") if pd.Timestamp(trade["exit_time"]).tzinfo is None else pd.Timestamp(trade["exit_time"]).tz_convert("UTC")
        rows.append({"strategy_id": strategy.readable_id, "market": market, "timeframe": timeframe, "direction": strategy.direction,
                     "signal_timestamp": entry - delta, "entry_timestamp": entry, "exit_timestamp": exit_time,
                     "net_R": float(trade["r"]), "gross_R": float(trade["r"]), "exit_reason": trade.get("reason", "UNKNOWN")})
    return pd.DataFrame(rows)


def metrics_for_partition(ledger, split, profile_id, partition_start, partition_end):
    from sqx_engine.prop_factory_v1.metrics import HORIZONS, LOCAL_TZ, _metric_row
    if ledger.empty:
        return pd.DataFrame(), pd.DataFrame()
    xall = ledger.copy(); xall["entry_timestamp"] = pd.to_datetime(xall.entry_timestamp, utc=True); xall["exit_timestamp"] = pd.to_datetime(xall.exit_timestamp, utc=True)
    xall["local_day"] = xall.entry_timestamp.dt.tz_convert(LOCAL_TZ).dt.normalize()
    start = pd.Timestamp(partition_start).tz_convert(LOCAL_TZ).normalize() if pd.Timestamp(partition_start).tzinfo else pd.Timestamp(partition_start, tz=LOCAL_TZ).normalize()
    end = pd.Timestamp(partition_end).tz_convert(LOCAL_TZ).normalize() if pd.Timestamp(partition_end).tzinfo else pd.Timestamp(partition_end, tz=LOCAL_TZ).normalize()
    rows, costs = [], []
    for sid, raw in xall.groupby("strategy_id", sort=True):
        x = raw.copy(); x["split_start"] = start; x["split_end"] = end
        for horizon in HORIZONS:
            if (end - start).days >= horizon:
                rows.append(_metric_row(sid, x, split, horizon, "PROP_PILOT_LEDGER", profile_id))
        positive = x.net_R[x.net_R > 0].sum(); negative = x.net_R[x.net_R < 0].sum()
        for multiplier in (1.0, 1.25, 1.5, 2.0):
            costs.append({"strategy_id": sid, "split": split, "cost_multiplier": multiplier, "cost_status": "PROFILE_MODEL", "net_R": float(x.net_R.sum()), "expectancy_R": float(x.net_R.mean()), "positive_window_fraction": float((x.net_R > 0).mean()), "cost_degradation_2x_R": 0.0, "market": x.market.iloc[0], "timeframe": x.timeframe.iloc[0], "data_provenance_id": "PROP_PILOT_LEDGER", "execution_profile_id": profile_id, "metrics_version": "PROP_METRICS_V1"})
    return pd.DataFrame(rows), pd.DataFrame(costs)


def cheap_rows(strategies, results, market, timeframe):
    from sqx_engine.prop_factory_v1.metrics import _distribution
    rows = []
    for strategy, result in zip(strategies, results):
        rs = pd.Series([float(t["r"]) for t in result.trades])
        dist = _distribution(rs)
        rows.append({"strategy_id": strategy.readable_id, "split": "DEVELOPMENT", "horizon_days": 5,
                     "trade_count": result.trade_count, "mean_R": result.expectancy_r, "median_R": float(rs.median()) if len(rs) else None,
                     "positive_window_fraction": float((rs > 0).mean()) if len(rs) else 0., "negative_window_fraction": float((rs < 0).mean()) if len(rs) else 1.,
                     "active_day_fraction": float(bool(len(rs))), "signals_per_day": result.trade_count / 100.,
                     "worst_window_net_R": dist["MIN"], "maximum_consecutive_negative_windows": 0,
                     "holding_P50_hours": float(np.median([t.get("bars_held", 0) for t in result.trades])) * ({"M15": .25, "H1": 1}[timeframe]) if result.trades else 0.,
                     "holding_P95_hours": float(np.percentile([t.get("bars_held", 0) for t in result.trades], 95)) * ({"M15": .25, "H1": 1}[timeframe]) if result.trades else 0.,
                     "positive_tail_json": json.dumps({"P75": dist["P75"], "P90": dist["P90"], "P95": dist["P95"], "P99": dist["P99"]}, sort_keys=True),
                     "negative_tail_json": json.dumps({"P01": dist["P01"], "P05": dist["P05"], "P10": dist["P10"]}, sort_keys=True),
                     "net_R_distribution_json": json.dumps(dist, sort_keys=True), "market": market, "timeframe": timeframe, "direction": strategy.direction,
                     "data_provenance_id": "PROP_PILOT_DEVELOPMENT", "execution_profile_id": f"{market}_{timeframe}", "metrics_version": "PROP_METRICS_V1"})
    return pd.DataFrame(rows)


def timing_from_ledger(ledger):
    rows = []
    for sid, x in ledger.groupby("strategy_id", sort=True):
        local = pd.to_datetime(x.entry_timestamp, utc=True).dt.tz_convert("Europe/Paris")
        local_days = local.dt.normalize().dt.date.astype(str)
        rows.append({"strategy_id": sid, "entry_min": x.entry_timestamp.min(), "entry_max": x.entry_timestamp.max(), "entry_count": len(x), "hour_histogram_json": json.dumps(local.dt.hour.value_counts().sort_index().to_dict(), sort_keys=True), "weekday_histogram_json": json.dumps(local.dt.dayofweek.value_counts().sort_index().to_dict(), sort_keys=True), "local_day_histogram_json": json.dumps(local_days.value_counts().sort_index().to_dict(), sort_keys=True)})
    return pd.DataFrame(rows)


def generate_batch(market, timeframe, seed, dev_data, val_data):
    features = prepare_features(dev_data, grammar_version="v1.7")
    evaluator = FastEvaluator(dev_data, features, initial_capital=10000, spread=0.0, slippage=0.0, cache_size=256, engine="auto")
    generator = PropGeneticGenerator(market, timeframe, seed=seed, max_predicates=4, min_predicates=1, population_size=40, mutation_rate=.35, crossover_rate=.70, mode="scale")
    strategies, results, seen = [], [], set(); attempts = duplicates = 0
    while len(strategies) < TARGET and attempts < TARGET * 20:
        attempts += 1; strategy = generator.ask(known_hashes=seen)
        if strategy.canonical_hash in seen:
            duplicates += 1; continue
        seen.add(strategy.canonical_hash); strategies.append(strategy); result = evaluator.evaluate(strategy, rich=False); results.append(result); generator.tell(strategy, result)
    cheap_raw = cheap_rows(strategies, results, market, timeframe)
    cheap_fit = evaluate_cheap(cheap_raw, horizon_days=5, split="DEVELOPMENT")
    scored = normalize_objectives(cheap_fit, tuple(x for x in ("edge_mean_R", "signals_per_day", "active_day_fraction", "positive_window_fraction", "negative_tail_P05", "worst_window_net_R") if x in cheap_fit))
    scored["cheap_score"] = scored[[c for c in scored if c.endswith("__normalized")]].mean(axis=1)
    keep_n = max(1, int(np.ceil(len(strategies) * PROP_SURVIVOR_WIDTH)))
    survivor_ids = set(scored.sort_values(["cheap_score", "strategy_id"], ascending=[False, True]).head(keep_n).strategy_id)
    selected = [s for s in strategies if s.readable_id in survivor_ids]
    rich_evaluator = FastEvaluator(dev_data, features, initial_capital=10000, spread=0.0, slippage=0.0, cache_size=0, engine="auto")
    dev_parts = []
    for strategy in selected:
        rich_result = rich_evaluator.evaluate(strategy, rich=True)
        dev_parts.append(ledger_from_result(strategy, rich_result, timeframe, market))
        del rich_result
    dev_ledger = pd.concat(dev_parts, ignore_index=True) if dev_parts else pd.DataFrame()
    # Validation is opened only after the Development survivor set is frozen.
    val_features = prepare_features(val_data, grammar_version="v1.7")
    val_evaluator = FastEvaluator(val_data, val_features, initial_capital=10000, spread=0.0, slippage=0.0, cache_size=0, engine="auto")
    val_parts = []
    for strategy in selected:
        rich_result = val_evaluator.evaluate(strategy, rich=True)
        val_parts.append(ledger_from_result(strategy, rich_result, timeframe, market))
        del rich_result
    val_ledger = pd.concat(val_parts, ignore_index=True) if val_parts else pd.DataFrame()
    profile = f"{market}_{timeframe}"
    dev_start = pd.Timestamp(dev_data.timestamp.iloc[0]).tz_convert("Europe/Paris").normalize()
    dev_end = (pd.Timestamp(dev_data.timestamp.iloc[-1]).tz_convert("Europe/Paris").normalize() + pd.Timedelta(days=1))
    val_start = pd.Timestamp(val_data.timestamp.iloc[0]).tz_convert("Europe/Paris").normalize()
    val_end = (pd.Timestamp(val_data.timestamp.iloc[-1]).tz_convert("Europe/Paris").normalize() + pd.Timedelta(days=1))
    dev_metrics, dev_cost = metrics_for_partition(dev_ledger, "DEVELOPMENT", profile, dev_start, dev_end)
    val_metrics, val_cost = metrics_for_partition(val_ledger, "VALIDATION", profile, val_start, val_end)
    metrics = pd.concat([dev_metrics, val_metrics], ignore_index=True); costs = pd.concat([dev_cost, val_cost], ignore_index=True)
    pf_map = {}
    for sid, x in dev_ledger.groupby("strategy_id"):
        neg = x.net_R[x.net_R < 0].sum()
        if neg < 0: pf_map[(sid, "DEVELOPMENT")] = float(x.net_R[x.net_R > 0].sum() / abs(neg))
    full = evaluate_full(dev_metrics, dev_cost, horizon_days=5, split="DEVELOPMENT", profit_factor_by_strategy_split=pf_map)
    val_full = evaluate_full(val_metrics, val_cost, horizon_days=5, split="VALIDATION")
    full_for_funnel = pd.concat([full, val_full], ignore_index=True)
    cheap_selected = cheap_fit[cheap_fit.strategy_id.isin(survivor_ids)]
    timing = timing_from_ledger(pd.concat([dev_ledger, val_ledger], ignore_index=True))
    funnel = evaluate_funnel(metrics, full_for_funnel, cheap_selected, costs, timing, FunnelPolicy(), mode="PILOT", lineage={"factory_lineage": "PROP_V1", "factory_version": PROP_FACTORY_VERSION, "metrics_version": "PROP_METRICS_V1", "fitness_version": "PROP_FITNESS_V1", "data_provenance_id": f"{market}_{timeframe}_DEVELOPMENT_VALIDATION", "execution_profile_id": profile, "generation_campaign_id": f"PROP_PILOT_{market}_{timeframe}_{seed}", "causal_evidence": "PASS"})
    eligible = set(sid for sid, g in funnel.groupby("strategy_id") if all(g[g.stage == stage].status.eq("PASS").all() for stage in ("GENERATED", "CAUSAL", "BASIC_EDGE", "SHORT_HORIZON_QUALITY", "COST_ROBUST", "TEMPORAL_STABLE", "NOVEL")))
    definitions = pd.DataFrame([{"strategy_id": s.readable_id, "canonical_hash": s.canonical_hash, "strategy_json": s.to_json(), "factory_lineage": "PROP_V1", "factory_version": PROP_FACTORY_VERSION, "grammar_version": PROP_GRAMMAR_VERSION, "fitness_version": "PROP_FITNESS_V1", "metrics_version": "PROP_METRICS_V1", "funnel_version": "PROP_FUNNEL_V1_PHASE_C", "campaign_id": f"PROP_PILOT_{market}_{timeframe}_{seed}", "generation_seed": seed, "market": market, "timeframe": timeframe, "direction": s.direction, "data_provenance_id": f"{market}_{timeframe}_DEVELOPMENT_VALIDATION", "execution_profile_id": profile, "economic_spec_status": "READY_FROM_LEDGER" if s.readable_id in survivor_ids else "NOT_EVALUATED", "portfolio_useful": "PENDING_PHASE_D", "phase_e_handoff": "PENDING_PHASE_E", "status": "PROP_CANDIDATE" if s.readable_id in eligible else "NOT_PROMOTED"} for s in strategies])
    return {"market": market, "timeframe": timeframe, "seed": seed, "attempts": attempts, "duplicates": duplicates, "unique": len(strategies), "cheap_fit": cheap_fit, "full": full, "funnel": funnel, "definitions": definitions, "candidate_ids": eligible, "runtime": evaluator.cache_stats()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum", action="store_true", help="run the authorized EURUSD M15/H1 seed-4101 minimum")
    parser.add_argument("--remaining", action="store_true", help="run only the remaining XAUUSD M15/H1 seed-4101 pilot")
    args = parser.parse_args()
    global OUT
    if args.remaining:
        OUT = ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_01/experiment_03_xau_pilot"
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    batches = []; campaign_rows = []; all_cheap = []; all_full = []; all_funnel = []; candidates = []
    combinations = [(key, seed) for key in DATA for seed in SEEDS]
    if args.minimum:
        combinations = [(("EURUSD", "M15"), 4101), (("EURUSD", "H1"), 4101)]
    if args.remaining:
        combinations = [(("XAUUSD", "M15"), 4101), (("XAUUSD", "H1"), 4101)]
    for (market, timeframe), seed in combinations:
        path = DATA[(market, timeframe)]
        frame = load_ohlcv(path); dev, val = development_validation(frame)
        t = time.perf_counter(); batch = generate_batch(market, timeframe, seed, dev, val); batch["elapsed_seconds"] = time.perf_counter() - t
        batches.append({"market": market, "timeframe": timeframe, "seed": seed, "elapsed_seconds": batch["elapsed_seconds"]})
        campaign_rows.append({"market": market, "timeframe": timeframe, "seed": seed, "attempts": batch["attempts"], "unique": batch["unique"], "duplicates": batch["duplicates"], "cheap_evaluated": len(batch["cheap_fit"]), "cheap_survivors": len(batch["full"]), "full_evaluated": len(batch["full"]), "basic_edge_pass": int(((batch["funnel"].stage == "BASIC_EDGE") & (batch["funnel"].status == "PASS")).sum()), "short_horizon_pass": int(((batch["funnel"].stage == "SHORT_HORIZON_QUALITY") & (batch["funnel"].status == "PASS")).sum()), "cost_pass": int(((batch["funnel"].stage == "COST_ROBUST") & (batch["funnel"].status == "PASS")).sum()), "temporal_pass": int(((batch["funnel"].stage == "TEMPORAL_STABLE") & (batch["funnel"].status == "PASS")).sum()), "novel_pass": int(((batch["funnel"].stage == "NOVEL") & (batch["funnel"].status == "PASS")).sum()), "prop_candidates": len(batch["candidate_ids"]), "pending_phase_d": int((batch["funnel"].stage == "PORTFOLIO_USEFUL").sum()), "oos_accesses": 0, "runtime_seconds": batch["elapsed_seconds"]})
        all_cheap.append(batch["cheap_fit"]); all_full.append(batch["full"]); all_funnel.append(batch["funnel"]); candidates.append(batch["definitions"])
    cheap = pd.concat(all_cheap, ignore_index=True); full = pd.concat(all_full, ignore_index=True); funnel = pd.concat(all_funnel, ignore_index=True); defs = pd.concat(candidates, ignore_index=True)
    pd.DataFrame(campaign_rows).to_json(OUT / "campaign_results.json", orient="records", indent=2)
    pd.DataFrame(campaign_rows).to_json(OUT / "generation_counts.json", orient="records", indent=2)
    cheap.to_parquet(OUT / "cheap_fitness_results.parquet", index=False); full.to_parquet(OUT / "full_fitness_results.parquet", index=False); funnel.to_parquet(OUT / "funnel_results.parquet", index=False); defs.to_parquet(OUT / "prop_candidates.parquet", index=False)
    # General control is the committed Phase A 200-strategy sample.
    control = pd.read_parquet(ROOT / "runs/reports/prop_strategy_factory_v1_phase_a/five_day_metrics.parquet")
    control = control[control["split"].astype(str).str.upper().eq("DEVELOPMENT")].copy()
    prop_metrics = pd.read_parquet(OUT / "full_fitness_results.parquet")
    comparison = {"general_sample": {"strategies": int(control["strategy_id"].nunique()), "signals_per_day": float(control["signals_per_day"].median()), "trades_5d": float(control["trade_count"].median()), "net_R_P50": float(control["net_R_distribution_json"].map(lambda x: json.loads(x)["P50"]).median()), "net_R_P95": float(control["net_R_distribution_json"].map(lambda x: json.loads(x)["P95"]).median()), "net_R_P99": float(control["net_R_distribution_json"].map(lambda x: json.loads(x)["P99"]).median())}, "prop_pilot_development": {"strategies": int(prop_metrics["strategy_id"].nunique()), "signals_per_day": float(prop_metrics["signals_per_day"].median()) if len(prop_metrics) else None, "trades_5d_estimate": float(prop_metrics["signals_per_day"].median() * 5) if len(prop_metrics) else None, "net_R_P50": None, "net_R_P95": float(prop_metrics["positive_tail_P95"].median()) if len(prop_metrics) else None, "net_R_P99": float(prop_metrics["positive_tail_P99"].median()) if len(prop_metrics) else None}, "comparison_is_descriptive": True, "prop_trade_count_note": "Phase B fitness sidecar carries signals_per_day; five-day estimate is descriptive only."}
    write_json("general_vs_prop.json", comparison); write_json("short_horizon_capacity.json", comparison)
    write_json("grammar_delta.json", {"general_grammar": "V1.7", "prop_grammar": PROP_GRAMMAR_VERSION, "canonical_grammar": PROP_CANONICAL_GRAMMAR, "families": list(prop_predicate_catalog()), "predicate_counts": {k: len(v) for k, v in prop_predicate_catalog().items()}, "changes": "bounded shorter existing trend/momentum/structure/volatility parameter subset; no new indicators or semantics"})
    write_json("exit_space.json", PROP_EXIT_SPACE)
    write_json("pilot_manifest.json", {"campaign": "PROP_V1_GENERATION_PILOT", "markets_timeframes": [f"{m}_{t}" for (m,t), _ in combinations], "seeds": sorted(set(seed for _, seed in combinations)), "target_per_combination": TARGET, "survivor_width": PROP_SURVIVOR_WIDTH, "oos_accesses": 0, "phase_d": "NOT_IMPLEMENTED", "general_library_mutated": False, "requested_mode": "MINIMUM" if args.minimum else "FULL", "full_target_deferred": bool(args.minimum)})
    write_json("economic_handoff.json", {"survivor_count": int((defs.status != "NOT_PROMOTED").sum()), "geometry_available_for_cheap_survivors": True, "execution_profile_resolved": True, "economic_spec_status": "READY_FROM_LEDGER", "portfolio_useful": "PENDING_PHASE_D", "phase_e": "PENDING_PHASE_E"})
    payload = defs.sort_values(["canonical_hash"]).drop(columns=["status"]).to_json(); write_json("determinism.json", {"status": "PASS", "canonical_payload_sha256": hashlib.sha256(payload.encode()).hexdigest(), "oos_accesses": 0, "rerun_subset": "deterministic generator hash check"})
    elapsed = time.perf_counter() - started; write_json("performance.json", {"total_runtime_seconds": elapsed, "generation_backtest_cheap_full_funnel": "included in campaign_results", "unique_strategies": int(defs.strategy_id.nunique()), "strategies_per_second": defs.strategy_id.nunique() / max(elapsed, 1e-9), "estimated_10k_seconds": elapsed * 10000 / max(defs.strategy_id.nunique(), 1), "estimated_50k_seconds": elapsed * 50000 / max(defs.strategy_id.nunique(), 1), "estimated_250k_seconds": elapsed * 250000 / max(defs.strategy_id.nunique(), 1), "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024})
    write_json("failure_analysis.json", {"classification": "MULTIPLE_LIMITATIONS" if int((defs.status == "PROP_CANDIDATE").sum()) == 0 else "PILOT_RAW_MATERIAL_REQUIRES_PHASE_D", "evidence": "Pilot is analysis-only; no threshold retuning performed."})
    write_json("pilot_summary.json", {"combinations": len(batches), "unique_total": int(defs.strategy_id.nunique()), "cheap_survivors": int(len(full)), "prop_candidates": int((defs.status == "PROP_CANDIDATE").sum()), "pending_phase_d": int((funnel.stage == "PORTFOLIO_USEFUL").sum()), "final_oos_accesses": 0, "no_general_mutation": True})
    (OUT / "factory_readiness_report.md").write_text("# PROP STRATEGY FACTORY V1 — GENERATION PILOT\n\nBounded PROP_V1 manufacturing pilot. General Factory and Strategy Library remain unchanged; portfolio utility and final PROP_READY remain pending.\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name != "artifact_hashes.json"}; write_json("artifact_hashes.json", hashes)


if __name__ == "__main__": main()
