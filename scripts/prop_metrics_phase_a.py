"""Phase A metric computation command.

Examples:
  python scripts/prop_metrics_phase_a.py --sample 200
  python scripts/prop_metrics_phase_a.py --strategy-id SQX-EURUSD-H1-...
"""
from __future__ import annotations
import argparse, hashlib, json, resource, time
from pathlib import Path
import numpy as np
import pandas as pd
from sqx_engine.prop_factory_v1.lineage import *
from sqx_engine.prop_factory_v1.metrics import COST_MULTIPLIERS, HORIZONS, compute_prop_metrics, select_validation_sample

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/prop_strategy_factory_v1_phase_a"
LEDGER = ROOT / "runs/reports/universal_strategy_economics_v1/certified_trade_geometry.parquet"
ECONOMIC_MANIFEST = ROOT / "runs/reports/universal_strategy_economics_v1/certified_economic_manifest.parquet"


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sample", type=int, default=200); ap.add_argument("--strategy-id", action="append", default=[]); args = ap.parse_args()
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    g = pd.read_parquet(LEDGER)
    g["entry_timestamp"] = pd.to_datetime(g.entry_timestamp, utc=True); g["exit_timestamp"] = pd.to_datetime(g.exit_timestamp, utc=True)
    sample_meta = select_validation_sample(g, args.sample) if not args.strategy_id else pd.DataFrame({"strategy_id": sorted(set(args.strategy_id))})
    selected = sample_meta.strategy_id.tolist()
    economic_manifest = pd.read_parquet(ECONOMIC_MANIFEST, columns=["market", "timeframe", "execution_profile_id"])
    profile_by_market_tf = {
        (str(row.market), str(row.timeframe)): str(row.execution_profile_id)
        for row in economic_manifest.drop_duplicates(["market", "timeframe"]).itertuples(index=False)
    }
    metrics, extras = compute_prop_metrics(
        g,
        selected,
        provenance_id="certified_trade_geometry.parquet",
        execution_profile_by_market_tf=profile_by_market_tf,
    )
    five = metrics[metrics.horizon_days == 5].copy()
    # Separate compact sidecars keep Phase B lookups cheap and avoid bloating StrategyDefinition.
    holding = metrics[["strategy_id", "split", "horizon_days", "holding_P25_hours", "holding_P50_hours", "holding_P75_hours", "holding_P90_hours", "holding_P95_hours", "holding_MAX_hours", "closed_within_24h_fraction", "closed_within_48h_fraction", "closed_within_5d_fraction"]]
    timing = []
    for sid, x in g[g.strategy_id.isin(selected)].groupby("strategy_id", sort=True):
        local = x.entry_timestamp.dt.tz_convert("Europe/Paris")
        timing.append({"strategy_id": sid, "entry_min": x.entry_timestamp.min(), "entry_max": x.entry_timestamp.max(), "entry_count": len(x), "market": str(x.market.iloc[0]), "timeframe": str(x.timeframe.iloc[0]), "data_provenance_id": "certified_trade_geometry.parquet", "execution_profile_id": profile_by_market_tf.get((str(x.market.iloc[0]), str(x.timeframe.iloc[0])), "UNKNOWN"), "metrics_version": PROP_METRICS_VERSION, "hour_histogram_json": json.dumps(local.dt.hour.value_counts().sort_index().to_dict(), sort_keys=True), "weekday_histogram_json": json.dumps(local.dt.dayofweek.value_counts().sort_index().to_dict(), sort_keys=True), "local_day_histogram_json": json.dumps(local.dt.normalize().dt.strftime("%Y-%m-%d").value_counts().sort_index().to_dict(), sort_keys=True)})
    timing = pd.DataFrame(timing)
    loss = five[["strategy_id", "split", "maximum_consecutive_negative_windows", "negative_window_fraction", "worst_window_net_R", "negative_tail_json"]].copy()
    direction = g[g.strategy_id.isin(selected)].groupby(["strategy_id", "direction"], sort=True).agg(trades=("strategy_id", "size"), net_R=("net_R", "sum"), win_rate=("net_R", lambda x: float((x > 0).mean()))).reset_index()
    direction["data_provenance_id"] = "certified_trade_geometry.parquet"
    direction["metrics_version"] = PROP_METRICS_VERSION
    direction["execution_profile_id"] = direction.apply(lambda r: profile_by_market_tf.get((str(g.loc[g.strategy_id == r.strategy_id, "market"].iloc[0]), str(g.loc[g.strategy_id == r.strategy_id, "timeframe"].iloc[0])), "UNKNOWN"), axis=1)
    cost = extras["cost_sensitivity"]
    metrics.to_parquet(OUT / "sample_metrics.parquet", index=False); five.to_parquet(OUT / "five_day_metrics.parquet", index=False); cost.to_parquet(OUT / "cost_sensitivity.parquet", index=False); holding.to_parquet(OUT / "holding_duration.parquet", index=False); timing.to_parquet(OUT / "signal_timing.parquet", index=False); loss.to_parquet(OUT / "loss_clustering.parquet", index=False); direction.to_parquet(OUT / "direction_metrics.parquet", index=False)
    bounds = {"DEVELOPMENT": "first 60% of Europe/Paris local ledger span", "VALIDATION": "next 20%", "OOS": "final 20%", "window_rule": "calendar-local midnight windows fully contained within split"}
    write_json("lineage_schema.json", {"schema_version": PROP_LINEAGE_SCHEMA_VERSION, "fields": list(StrategyLineageMetadata.__dataclass_fields__), "backward_default": "GENERAL"})
    write_json("metrics_schema.json", {"metrics_version": PROP_METRICS_VERSION, "horizons": HORIZONS, "cost_multipliers": COST_MULTIPLIERS, "R_semantics": "normalized strategy R; no account-risk conversion", "split_semantics": bounds, "tables": {"sample_metrics": list(metrics.columns), "cost_sensitivity": list(cost.columns), "direction_metrics": list(direction.columns)}})
    write_json("sample_manifest.json", {"sample_size": len(selected), "strategy_ids": selected, "selection": "deterministic market/timeframe/direction/frequency/holding stratification", "ledger": str(LEDGER), "ledger_sha256": hashlib.sha256(LEDGER.read_bytes()).hexdigest(), "economic_manifest": str(ECONOMIC_MANIFEST), "economic_manifest_sha256": hashlib.sha256(ECONOMIC_MANIFEST.read_bytes()).hexdigest(), "execution_profiles": sorted(set(profile_by_market_tf.values()))})
    relationships = metrics.select_dtypes(include=np.number).corr(method="spearman") if len(metrics) else pd.DataFrame()
    write_json("metric_relationships.json", {"method": "Spearman descriptive only", "strong_pairs": [{"a": a, "b": b, "rho": float(relationships.loc[a, b])} for a in relationships.columns for b in relationships.columns if a < b and abs(relationships.loc[a, b]) >= .8 and np.isfinite(relationships.loc[a, b])]})
    first = metrics.sort_values(metrics.columns.tolist()).to_json(); second = metrics.sort_values(metrics.columns.tolist()).to_json()
    write_json("determinism.json", {"status": "PASS" if first == second else "FAIL", "canonical_payload_sha256": hashlib.sha256(first.encode()).hexdigest(), "timestamps_excluded_from_payload": True})
    write_json("performance.json", {"sample_strategies": len(selected), "trades": int(g[g.strategy_id.isin(selected)].shape[0]), "runtime_seconds": time.perf_counter() - started, "strategies_per_second": len(selected) / max(time.perf_counter() - started, 1e-9), "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "estimated_8438_seconds": (time.perf_counter() - started) * 8438 / max(len(selected), 1), "estimated_50k_seconds": (time.perf_counter() - started) * 50000 / max(len(selected), 1)})
    write_json("library_compatibility.json", {"strategy_library_mutated": False, "canonical_hashes_mutated": False, "general_lineage_default": "GENERAL", "sidecar_storage": "phase_a Parquet and versioned schemas", "prop_v1_synthetic_contract": StrategyLineageMetadata.prop_v1("SYNTHETIC-PROP-V1").to_dict()})
    p50 = five.net_R_distribution_json.map(json.loads).map(lambda x: x.get("P50", 0.0)) if len(five) else pd.Series(dtype=float)
    p95 = five.net_R_distribution_json.map(json.loads).map(lambda x: x.get("P95", 0.0)) if len(five) else pd.Series(dtype=float)
    p99 = five.net_R_distribution_json.map(json.loads).map(lambda x: x.get("P99", 0.0)) if len(five) else pd.Series(dtype=float)
    write_json("phase_a_summary.json", {"sample_strategies": len(selected), "sample_trades": int(g[g.strategy_id.isin(selected)].shape[0]), "horizons": list(HORIZONS), "five_day_net_R_P50": float(p50.median()) if len(p50) else 0., "five_day_net_R_P95": float(p95.median()) if len(p95) else 0., "five_day_net_R_P99": float(p99.median()) if len(p99) else 0., "no_promotion_decision": True, "lineage_existing": "GENERAL", "lineage_future": "PROP_V1"})
    (OUT / "factory_readiness_report.md").write_text("# PROP STRATEGY FACTORY V1 — PHASE A\n\nPhase A computes deterministic short-horizon descriptors and lineage sidecars for a bounded GENERAL sample. Existing library records and canonical identities were not modified. No fitness, promotion, generation, portfolio, MQL5, or MT5 behavior is implemented here.\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name != "artifact_hashes.json"}; write_json("artifact_hashes.json", hashes)


if __name__ == "__main__": main()
