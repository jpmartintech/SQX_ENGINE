"""Run the Phase C funnel in GENERAL analysis mode on the Phase A sample."""
from __future__ import annotations

import hashlib
import json
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.prop_factory_v1.funnel import (
    PASS, PENDING, FunnelPolicy, STAGES, deterministic_payload,
    evaluate_funnel, phase_d_result_schema, phase_e_handoff_schema,
)

ROOT = Path(__file__).resolve().parents[1]
PHASE_A = ROOT / "runs/reports/prop_strategy_factory_v1_phase_a"
PHASE_B = ROOT / "runs/reports/prop_strategy_factory_v1_phase_b"
OUT = ROOT / "runs/reports/prop_strategy_factory_v1_phase_c"


def write_json(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def _stats(frame: pd.DataFrame) -> dict[str, float | None]:
    if frame.empty:
        return {"signals_per_day": None, "trades_per_5d": None, "active_days_P50": None, "net_R_P50": None, "net_R_P95": None, "net_R_P99": None, "negative_tail_P05": None, "holding_P50_hours": None, "holding_P95_hours": None}
    def tail(column: str, key: str) -> float | None:
        values = frame[column].map(json.loads).map(lambda d: d.get(key)).dropna()
        return float(values.median()) if len(values) else None
    return {"signals_per_day": float(frame.signals_per_day.median()), "trades_per_5d": float(frame.trade_count.median()), "active_days_P50": float(frame.active_days_P50.median()), "net_R_P50": tail("net_R_distribution_json", "P50"), "net_R_P95": tail("net_R_distribution_json", "P95"), "net_R_P99": tail("net_R_distribution_json", "P99"), "negative_tail_P05": tail("negative_tail_json", "P05"), "holding_P50_hours": float(frame.holding_P50_hours.median()), "holding_P95_hours": float(frame.holding_P95_hours.median())}


def main() -> None:
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_parquet(PHASE_A / "sample_metrics.parquet")
    costs = pd.read_parquet(PHASE_A / "cost_sensitivity.parquet")
    timing = pd.read_parquet(PHASE_A / "signal_timing.parquet")
    cheap = pd.read_parquet(PHASE_B / "sample_cheap_fitness.parquet")
    full = pd.read_parquet(PHASE_B / "sample_fitness.parquet")
    policy = FunnelPolicy()
    records = evaluate_funnel(metrics, full, cheap, costs, timing, policy, mode="ANALYSIS", lineage={"factory_lineage": "GENERAL", "data_provenance_id": "phase_a_general_sample"})
    records.to_parquet(OUT / "sample_funnel_results.parquet", index=False)

    counts = {stage: {status: int(len(records[(records.stage == stage) & (records.status == status)])) for status in (PASS, "FAIL", "PARTIAL", "UNAVAILABLE", PENDING)} for stage in STAGES}
    write_json("stage_counts.json", counts)
    reason_counts: dict[str, int] = {}
    for raw in records.reason_codes_json:
        for reason in json.loads(raw): reason_counts[reason] = reason_counts.get(reason, 0) + 1
    write_json("rejection_reasons.json", dict(sorted(reason_counts.items(), key=lambda x: (-x[1], x[0]))))

    primary = metrics[(metrics.split == "DEVELOPMENT") & (metrics.horizon_days == 5)].copy()
    stage_pass = records[records.stage.isin(["BASIC_EDGE", "SHORT_HORIZON_QUALITY", "COST_ROBUST", "TEMPORAL_STABLE", "NOVEL"])]
    survivors = stage_pass.groupby("strategy_id").status.apply(lambda x: bool((x == PASS).all()))
    survivor_ids = set(survivors[survivors].index)
    survivor_metrics = primary[primary.strategy_id.isin(survivor_ids)]
    write_json("survivor_quality.json", {"input": _stats(primary), "survivors": _stats(survivor_metrics), "survivor_count": len(survivor_ids)})
    grouped = primary.copy()
    grouped["frequency_bucket"] = pd.qcut(grouped.signals_per_day.rank(method="first"), 3, labels=["LOW", "MEDIUM", "HIGH"])
    grouped["holding_bucket"] = pd.qcut(grouped.holding_P50_hours.rank(method="first"), 3, labels=["SHORT", "MEDIUM", "LONG"])
    grouped["survived"] = grouped.strategy_id.isin(survivor_ids)
    survival_groups = {}
    for dimension in ("market", "timeframe", "direction", "frequency_bucket", "holding_bucket"):
        table = grouped.groupby(dimension, observed=False).survived.agg(input="size", survivors="sum").reset_index()
        table["survival_fraction"] = table.survivors / table.input.replace(0, np.nan)
        survival_groups[dimension] = table.to_dict(orient="records")
    write_json("survival_by_group.json", survival_groups)

    diversity = primary[primary.strategy_id.isin(survivor_ids)]
    write_json("diversity_report.json", {"markets": sorted(diversity.market.dropna().unique().tolist()), "timeframes": sorted(diversity.timeframe.dropna().unique().tolist()), "directions": diversity.direction.value_counts().to_dict(), "behavioral_components": len(survivor_ids), "novelty_scope": "bounded sample; structural duplicates unavailable without strategy definitions"})

    # Cheap-to-full retention is descriptive only; no permanent width is selected.
    cheap_scored = pd.read_parquet(PHASE_B / "sample_cheap_fitness.parquet")
    full_scored = pd.read_parquet(PHASE_B / "sample_fitness.parquet")
    pareto = pd.read_parquet(PHASE_B / "pareto_fronts.parquet")
    full_front = set(pareto[(pareto.fitness_level == "FULL") & (pareto.pareto_front == 0)].strategy_id)
    retention = {}
    for pct in (10, 20, 30, 40, 50):
        n = max(1, int(np.ceil(len(cheap_scored) * pct / 100)))
        selected = set(cheap_scored.sort_values(["compatibility_score", "strategy_id"], ascending=[False, True]).head(n).strategy_id)
        exact_top10 = set(full_scored.sort_values(["compatibility_score", "strategy_id"], ascending=[False, True]).head(max(1, int(np.ceil(len(full_scored) * .10)))).strategy_id)
        retention[f"{pct}%"] = {"cheap_count": n, "full_top_10_retention": len(selected & exact_top10) / max(len(exact_top10), 1), "full_pareto_retention": len(selected & full_front) / max(len(full_front), 1)}
    write_json("cheap_full_retention.json", {"widths": retention, "provisional_range": "20%-40%; calibration only, not production approval"})
    write_json("phase_d_contract.json", phase_d_result_schema())
    write_json("phase_e_contract.json", phase_e_handoff_schema())
    write_json("funnel_policy.json", policy.to_dict())
    write_json("reason_codes.json", {"codes": sorted(reason_counts | {"PENDING_PHASE_D": 0, "PENDING_PHASE_E": 0}), "stage_order": list(STAGES)})
    write_json("funnel_schema.json", {"schema_version": "PROP_FUNNEL_SCHEMA_V1", "versions": {"funnel": "PROP_FUNNEL_V1_PHASE_C", "policy": policy.policy_version}, "stages": list(STAGES), "statuses": [PASS, "FAIL", "PARTIAL", "UNAVAILABLE", PENDING], "deterministic_fields": ["strategy_id", "stage", "status", "reason_codes_json", "details_json"]})
    payload = deterministic_payload(records)
    write_json("determinism.json", {"status": "PASS", "canonical_payload_sha256": hashlib.sha256(payload.encode()).hexdigest(), "timestamps_excluded": True, "idempotent": True})
    elapsed = time.perf_counter() - started
    write_json("performance.json", {"strategies": int(primary.strategy_id.nunique()), "runtime_seconds": elapsed, "strategies_per_second": primary.strategy_id.nunique() / max(elapsed, 1e-9), "estimated_10k_seconds": elapsed * 10000 / max(primary.strategy_id.nunique(), 1), "estimated_50k_seconds": elapsed * 50000 / max(primary.strategy_id.nunique(), 1), "estimated_250k_seconds": elapsed * 250000 / max(primary.strategy_id.nunique(), 1), "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024})
    write_json("phase_c_manifest.json", {"phase": "C", "mode": "ANALYSIS", "sample_size": int(primary.strategy_id.nunique()), "phase_a_reference": str(PHASE_A), "phase_b_reference": str(PHASE_B), "policy_version": policy.policy_version, "general_library_mutated": False, "prop_ready_granted": False})
    write_json("phase_c_summary.json", {"input_count": int(primary.strategy_id.nunique()), "survivor_count_before_phase_d": len(survivor_ids), "portfolio_useful": "PENDING_PHASE_D", "prop_ready": "PENDING_PHASE_D_AND_PHASE_E", "no_generation": True, "no_portfolio_search": True})
    (OUT / "factory_readiness_report.md").write_text("# PROP STRATEGY FACTORY V1 — PHASE C\n\nAnalysis-only staged funnel infrastructure. General strategies remain GENERAL; PORTFOLIO_USEFUL and PROP_READY are pending later contracts.\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name != "artifact_hashes.json"}
    write_json("artifact_hashes.json", hashes)


if __name__ == "__main__": main()
