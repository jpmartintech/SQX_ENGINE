"""Re-evaluate the frozen pilot survivors with corrected Phase A semantics.

This consumes the previously generated deterministic strategy manifest and
does not generate new strategies or inspect OOS data.
"""
from __future__ import annotations
import importlib.util, json, time
from pathlib import Path
import pandas as pd
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.data.loader import load_ohlcv
from sqx_engine.features import prepare_features
from sqx_engine.prop_factory_v1.fitness import evaluate_full
from sqx_engine.prop_factory_v1.funnel import evaluate_funnel, FunnelPolicy
from sqx_engine.strategy import StrategyDefinition

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runs/reports/prop_strategy_factory_v1_generation_pilot"
OUT = ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_01/experiment_02_semantic_fix"
DATA = {
    ("EURUSD", "M15"): ROOT / "data/cloud/EURUSD_M15.csv",
    ("EURUSD", "H1"): ROOT / "data/derived/EURUSD_H1_11d571e8bb3d_143197.csv",
}

def load_pilot_module():
    spec = importlib.util.spec_from_file_location("prop_generation_pilot_v1", ROOT / "scripts/prop_generation_pilot_v1.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def main():
    pilot = load_pilot_module()
    OUT.mkdir(parents=True, exist_ok=True)
    definitions = pd.read_parquet(SOURCE / "prop_candidates.parquet")
    old_full = pd.read_parquet(SOURCE / "full_fitness_results.parquet")
    cheap = pd.read_parquet(SOURCE / "cheap_fitness_results.parquet")
    selected_ids = set(old_full.strategy_id)
    rows, full_rows, funnel_rows, timings = [], [], [], []
    started = time.perf_counter()
    for (market, timeframe), path in DATA.items():
        frame = load_ohlcv(path); dev, val = pilot.development_validation(frame)
        features = prepare_features(dev, grammar_version="v1.7")
        dev_eval = FastEvaluator(dev, features, initial_capital=10000, spread=0.0, slippage=0.0, cache_size=0, engine="auto")
        val_features = prepare_features(val, grammar_version="v1.7")
        val_eval = FastEvaluator(val, val_features, initial_capital=10000, spread=0.0, slippage=0.0, cache_size=0, engine="auto")
        group = definitions[(definitions.market == market) & (definitions.timeframe == timeframe) & definitions.strategy_id.isin(selected_ids)]
        strategies = [StrategyDefinition.from_json(x) for x in group.strategy_json]
        dev_parts, val_parts = [], []
        for strategy in strategies:
            dev_parts.append(pilot.ledger_from_result(strategy, dev_eval.evaluate(strategy, rich=True), timeframe, market))
        for strategy in strategies:
            val_parts.append(pilot.ledger_from_result(strategy, val_eval.evaluate(strategy, rich=True), timeframe, market))
        dev_ledger = pd.concat(dev_parts, ignore_index=True) if dev_parts else pd.DataFrame()
        val_ledger = pd.concat(val_parts, ignore_index=True) if val_parts else pd.DataFrame()
        profile = f"{market}_{timeframe}"
        ds = pd.Timestamp(dev.timestamp.iloc[0]).tz_convert("Europe/Paris").normalize(); de = pd.Timestamp(dev.timestamp.iloc[-1]).tz_convert("Europe/Paris").normalize() + pd.Timedelta(days=1)
        vs = pd.Timestamp(val.timestamp.iloc[0]).tz_convert("Europe/Paris").normalize(); ve = pd.Timestamp(val.timestamp.iloc[-1]).tz_convert("Europe/Paris").normalize() + pd.Timedelta(days=1)
        dm, dc = pilot.metrics_for_partition(dev_ledger, "DEVELOPMENT", profile, ds, de)
        vm, vc = pilot.metrics_for_partition(val_ledger, "VALIDATION", profile, vs, ve)
        pf_map = {}
        for sid, x in dev_ledger.groupby("strategy_id"):
            neg = x.net_R[x.net_R < 0].sum()
            if neg < 0: pf_map[(sid, "DEVELOPMENT")] = float(x.net_R[x.net_R > 0].sum() / abs(neg))
        full = evaluate_full(dm, dc, horizon_days=5, split="DEVELOPMENT", profit_factor_by_strategy_split=pf_map)
        val_full = evaluate_full(vm, vc, horizon_days=5, split="VALIDATION")
        timing = pilot.timing_from_ledger(pd.concat([dev_ledger, val_ledger], ignore_index=True))
        lineage = {"factory_lineage":"PROP_V1", "factory_version":"PROP_FACTORY_V1_PILOT", "metrics_version":"PROP_METRICS_V1", "fitness_version":"PROP_FITNESS_V1", "data_provenance_id":f"{market}_{timeframe}_DEVELOPMENT_VALIDATION", "execution_profile_id":profile, "generation_campaign_id":f"PROP_PILOT_REPLAY_{market}_{timeframe}", "causal_evidence":"PASS"}
        f = evaluate_funnel(pd.concat([dm, vm], ignore_index=True), pd.concat([full, val_full], ignore_index=True), cheap[cheap.strategy_id.isin(set(group.strategy_id))], pd.concat([dc, vc], ignore_index=True), timing, FunnelPolicy(), mode="PILOT_REPLAY", lineage=lineage)
        rows.append(pd.concat([dm, vm], ignore_index=True)); full_rows.append(full); funnel_rows.append(f); timings.append(timing)
    metrics = pd.concat(rows, ignore_index=True); full = pd.concat(full_rows, ignore_index=True); funnel = pd.concat(funnel_rows, ignore_index=True); timing = pd.concat(timings, ignore_index=True)
    metrics.to_parquet(OUT / "phase_a_metrics_complete.parquet", index=False); full.to_parquet(OUT / "full_fitness_results.parquet", index=False); funnel.to_parquet(OUT / "funnel_results.parquet", index=False); timing.to_parquet(OUT / "signal_timing.parquet", index=False)
    eligible = {sid for sid, g in funnel.groupby("strategy_id") if all(g[g.stage == s].status.eq("PASS").all() for s in ("GENERATED","CAUSAL","BASIC_EDGE","SHORT_HORIZON_QUALITY","COST_ROBUST","TEMPORAL_STABLE","NOVEL"))}
    definitions = definitions.copy(); definitions["semantic_replay_status"] = definitions.strategy_id.map(lambda x: "PROP_CANDIDATE" if x in eligible else "NOT_PROMOTED"); definitions.to_parquet(OUT / "prop_candidates_replay.parquet", index=False)
    summary = {"source_experiment":"PROP_V1_GENERATION_PILOT", "semantic_fix":"shared development/validation calendar boundaries; complete Phase A metrics retained in FULL sidecar", "strategies_replayed": int(full.strategy_id.nunique()), "prop_candidates": len(eligible), "oos_accesses": 0, "runtime_seconds": time.perf_counter()-started, "stage_counts": {stage:{status:int(n) for status,n in g.status.value_counts().items()} for stage,g in funnel.groupby("stage")}}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")

if __name__ == "__main__": main()
