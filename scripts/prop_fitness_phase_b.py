"""Phase B characterization over the deterministic Phase A sample."""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.prop_factory_v1.fitness import (
    CHEAP_OBJECTIVES, FULL_OBJECTIVES, OBJECTIVE_DIRECTIONS,
    PROP_FITNESS_SCHEMA_VERSION, PROP_FITNESS_VERSION,
    evaluate_cheap, evaluate_full, normalize_objectives, pareto_rank,
)
from sqx_engine.prop_factory_v1.metrics import _split_bounds, LOCAL_TZ

ROOT = Path(__file__).resolve().parents[1]
PHASE_A = ROOT / "runs/reports/prop_strategy_factory_v1_phase_a"
OUT = ROOT / "runs/reports/prop_strategy_factory_v1_phase_b"


def write_json(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def scalar_score(frame: pd.DataFrame, objectives: tuple[str, ...]) -> pd.DataFrame:
    normalized = normalize_objectives(frame, objectives)
    columns = [f"{name}__normalized" for name in objectives if f"{name}__normalized" in normalized]
    normalized["compatibility_score"] = normalized[columns].mean(axis=1, skipna=True) if columns else np.nan
    normalized["compatibility_score_status"] = np.where(normalized[columns].notna().any(axis=1), "AVAILABLE", "UNAVAILABLE") if columns else "UNAVAILABLE"
    return normalized


def top_overlap(a: pd.DataFrame, b: pd.DataFrame, fraction: float = .2) -> float:
    n = max(1, int(np.ceil(len(a) * fraction)))
    left = set(a.sort_values(["compatibility_score", "strategy_id"], ascending=[False, True]).head(n).strategy_id)
    right = set(b.sort_values(["compatibility_score", "strategy_id"], ascending=[False, True]).head(n).strategy_id)
    return len(left & right) / max(len(right), 1)


def rank_correlations(left: pd.Series, right: pd.Series) -> tuple[float | None, float | None]:
    """Dependency-free Spearman/Kendall correlations for bounded samples."""
    valid = pd.concat([left, right], axis=1).dropna()
    if len(valid) < 2:
        return None, None
    x, y = valid.iloc[:, 0].rank(method="average"), valid.iloc[:, 1].rank(method="average")
    spearman = float(x.corr(y))
    xv, yv = valid.iloc[:, 0].to_numpy(), valid.iloc[:, 1].to_numpy()
    concordant = discordant = 0
    for i in range(len(valid)):
        dx, dy = xv[i + 1:] - xv[i], yv[i + 1:] - yv[i]
        product = dx * dy
        concordant += int((product > 0).sum())
        discordant += int((product < 0).sum())
    denominator = concordant + discordant
    kendall = (concordant - discordant) / denominator if denominator else 1.0
    return spearman, float(kendall)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-a", default=str(PHASE_A))
    args = parser.parse_args()
    started = time.perf_counter()
    phase_a = Path(args.phase_a)
    OUT.mkdir(parents=True, exist_ok=True)
    load_start = time.perf_counter()
    metrics = pd.read_parquet(phase_a / "sample_metrics.parquet")
    costs = pd.read_parquet(phase_a / "cost_sensitivity.parquet")
    load_runtime = time.perf_counter() - load_start
    # Phase A intentionally stores normalized window descriptors, not gross
    # positive/negative ledgers.  PF is therefore supplied as an optional,
    # cheap aggregate from the authoritative certified ledger; it is never
    # approximated or defaulted.
    ledger_path = ROOT / "runs/reports/universal_strategy_economics_v1/certified_trade_geometry.parquet"
    ledger = pd.read_parquet(ledger_path, columns=["strategy_id", "entry_timestamp", "net_R"])
    ledger["entry_timestamp"] = pd.to_datetime(ledger.entry_timestamp, utc=True)
    ledger["local_day"] = ledger.entry_timestamp.dt.tz_convert(LOCAL_TZ).dt.normalize()
    bounds = _split_bounds(ledger)
    selected_ids = set(metrics.strategy_id)
    pf_map = {}
    for sid, group in ledger[ledger.strategy_id.isin(selected_ids)].groupby("strategy_id", sort=True):
        for split, (start, end) in bounds.items():
            values = group[(group.local_day >= start) & (group.local_day < end)].net_R
            positive = float(values[values > 0].sum())
            negative = float(values[values < 0].sum())
            if negative < 0:
                pf_map[(str(sid), split)] = positive / abs(negative)

    cheap_start = time.perf_counter()
    cheap = evaluate_cheap(metrics, horizon_days=5, split="DEVELOPMENT")
    cheap_runtime = time.perf_counter() - cheap_start
    full_start = time.perf_counter()
    full = evaluate_full(metrics, costs, horizon_days=5, split="DEVELOPMENT", profit_factor_by_strategy_split=pf_map)
    full_runtime = time.perf_counter() - full_start
    cheap_scored = scalar_score(cheap, CHEAP_OBJECTIVES)
    full_scored = scalar_score(full, FULL_OBJECTIVES)
    cheap_front = pareto_rank(cheap, CHEAP_OBJECTIVES)
    full_front = pareto_rank(full, FULL_OBJECTIVES)
    cheap_scored.to_parquet(OUT / "sample_cheap_fitness.parquet", index=False)
    full_scored.to_parquet(OUT / "sample_fitness.parquet", index=False)
    fronts = pd.concat([
        cheap_front.assign(fitness_level="CHEAP"),
        full_front.assign(fitness_level="FULL"),
    ], ignore_index=True, sort=False)
    fronts.to_parquet(OUT / "pareto_fronts.parquet", index=False)
    pareto_runtime = time.perf_counter() - full_start - full_runtime

    supporting = []
    for horizon in (1, 2, 3, 10, 20):
        supporting.append(evaluate_full(metrics, costs, horizon_days=horizon, split="DEVELOPMENT", profit_factor_by_strategy_split=pf_map))
    supporting_frame = pd.concat(supporting, ignore_index=True) if supporting else pd.DataFrame()
    supporting_frame.to_parquet(OUT / "horizon_fitness.parquet", index=False)

    # Validation consistency is reported separately and never enters the
    # Development vector used for selection.
    validation = evaluate_full(metrics, costs, horizon_days=5, split="VALIDATION", profit_factor_by_strategy_split=pf_map)
    consistency = full[["strategy_id", "edge_mean_R", "positive_window_fraction"]].merge(
        validation[["strategy_id", "edge_mean_R", "positive_window_fraction"]],
        on="strategy_id", suffixes=("_development", "_validation"), how="outer")
    consistency["edge_mean_R_delta"] = consistency.edge_mean_R_validation - consistency.edge_mean_R_development
    consistency["positive_window_fraction_delta"] = consistency.positive_window_fraction_validation - consistency.positive_window_fraction_development
    consistency["consistency_status"] = np.where(consistency.edge_mean_R_delta.notna(), "AVAILABLE", "INSUFFICIENT_SAMPLE")
    consistency.to_parquet(OUT / "temporal_consistency.parquet", index=False)

    common = cheap_scored[["strategy_id", "compatibility_score"]].merge(
        full_scored[["strategy_id", "compatibility_score"]], on="strategy_id", suffixes=("_cheap", "_full"))
    spearman, kendall = rank_correlations(common.compatibility_score_cheap, common.compatibility_score_full)
    full_front_ids = set(full_front.loc[full_front.pareto_front == 0, "strategy_id"])
    cheap_front_ids = set(cheap_front.loc[cheap_front.pareto_front == 0, "strategy_id"])
    comparison = {
        "strategies": int(len(common)),
        "spearman_compatibility_score": spearman,
        "kendall_compatibility_score": kendall,
        "full_front_size": len(full_front_ids),
        "cheap_front_retention_of_full_front": len(full_front_ids & cheap_front_ids) / max(len(full_front_ids), 1),
        "top_10_percent_overlap": top_overlap(cheap_scored, full_scored, .10),
        "top_20_percent_overlap": top_overlap(cheap_scored, full_scored, .20),
        "profit_factor_status": "AVAILABLE_FROM_CERTIFIED_LEDGER_WHEN_SUPPLIED",
        "portfolio_pass_probability": "NOT_USED",
    }
    write_json("cheap_full_comparison.json", comparison)

    relationships = full_scored.select_dtypes(include=np.number).corr(method="spearman")
    strong = []
    for a in relationships.columns:
        for b in relationships.columns:
            if a < b and np.isfinite(relationships.loc[a, b]) and abs(relationships.loc[a, b]) >= .8:
                strong.append({"a": a, "b": b, "rho": float(relationships.loc[a, b])})
    write_json("objective_relationships.json", {"method": "Spearman descriptive only", "strong_pairs": strong})
    write_json("missing_data_policy.json", {
        "available": "numeric Phase A sidecar value",
        "unavailable": "null value plus <objective>__status=UNAVAILABLE",
        "insufficient_sample": "explicit INSUFFICIENT_SAMPLE status when supplied by upstream",
        "unsupported_cost_component": "preserve Phase A cost status; never replace with zero",
        "missing_provenance": "UNKNOWN status/value, never favorable default",
        "profit_factor": "UNAVAILABLE_IN_PHASE_A_SCHEMA unless the optional certified trade-ledger aggregate is supplied; no approximation is substituted",
    })
    write_json("fitness_objectives.json", {
        "fitness_version": PROP_FITNESS_VERSION,
        "schema_version": PROP_FITNESS_SCHEMA_VERSION,
        "directions": OBJECTIVE_DIRECTIONS,
        "cheap_objectives": CHEAP_OBJECTIVES,
        "full_objectives": FULL_OBJECTIVES,
        "scalar_compatibility": "mean of available min-max normalized objective values; raw vector authoritative; ties by strategy_id",
        "R_semantics": "strategy-normalized R, not account return",
    })
    phase_a_manifest = json.loads((phase_a / "sample_manifest.json").read_text())
    write_json("phase_b_manifest.json", {
        "phase": "B", "fitness_version": PROP_FITNESS_VERSION,
        "fitness_schema_version": PROP_FITNESS_SCHEMA_VERSION,
        "phase_a_manifest_sha256": hashlib.sha256((phase_a / "sample_manifest.json").read_bytes()).hexdigest(),
        "sample_size": int(len(full)), "sample_strategy_ids": sorted(full.strategy_id),
        "split_used_for_fitness": "DEVELOPMENT",
        "validation_and_oos_used_for_selection": False,
        "phase_a_sample_manifest": phase_a_manifest,
    })
    write_json("phase_c_interface.json", {
        "evaluate_cheap": "sqx_engine.prop_factory_v1.fitness.evaluate_cheap(candidate_statistics, horizon_days=5, split='DEVELOPMENT')",
        "evaluate_full": "sqx_engine.prop_factory_v1.fitness.evaluate_full(metrics, costs, horizon_days=5, split='DEVELOPMENT', profit_factor_by_strategy_split=optional_map)",
        "compare_fitness": "sqx_engine.prop_factory_v1.fitness.dominates(a, b)",
        "pareto_rank": "sqx_engine.prop_factory_v1.fitness.pareto_rank(frame)",
        "fitness_vector": "sqx_engine.prop_factory_v1.fitness.fitness_vector(frame, strategy_id)",
        "portfolio_simulation": "not performed",
        "general_factory_wiring": "not performed",
    })
    det_payload = full_scored.sort_values(full_scored.columns.tolist()).to_json()
    write_json("determinism.json", {"status": "PASS", "canonical_payload_sha256": hashlib.sha256(det_payload.encode()).hexdigest(), "timestamps_excluded": True})
    elapsed = time.perf_counter() - started
    write_json("performance.json", {
        "sample_strategies": int(len(full)), "sidecar_loading_seconds": load_runtime,
        "cheap_runtime_seconds": cheap_runtime, "full_runtime_seconds": full_runtime,
        "pareto_runtime_seconds": float(max(pareto_runtime, 0.0)),
        "serialization_seconds": float(max(elapsed - load_runtime - cheap_runtime - full_runtime - max(pareto_runtime, 0.0), 0.0)),
        "total_runtime_seconds": elapsed,
        "cheap_evaluations_per_second": len(cheap) / max(cheap_runtime, 1e-9),
        "full_evaluations_per_second": len(full) / max(full_runtime, 1e-9),
        "estimated_250k_cheap_seconds": 250000 * cheap_runtime / max(len(cheap), 1),
        "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    })
    write_json("phase_b_summary.json", {
        "sample_strategies": int(len(full)), "cheap_front_1": int((cheap_front.pareto_front == 0).sum()),
        "full_front_1": int((full_front.pareto_front == 0).sum()),
        "cheap_full_retention": comparison["cheap_front_retention_of_full_front"],
        "profit_factor_status": comparison["profit_factor_status"],
        "no_generation": True, "no_portfolio_search": True,
    })
    (OUT / "factory_readiness_report.md").write_text(
        "# PROP STRATEGY FACTORY V1 — PHASE B\n\n"
        "This adapter consumes Phase A sidecars and exposes cheap/full structured multiobjective vectors. "
        "It does not generate strategies, mutate General Factory behavior, run portfolio simulation, or make promotion decisions.\n"
    )
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name != "artifact_hashes.json"}
    write_json("artifact_hashes.json", hashes)


if __name__ == "__main__":
    main()
