"""Phase C staged PROP promotion funnel.

This module evaluates existing metadata only.  It never mutates the Strategy
Library and deliberately leaves portfolio utility and final PROP_READY
handoff pending until later phases.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

import numpy as np
import pandas as pd

PROP_FUNNEL_VERSION = "PROP_FUNNEL_V1_PHASE_C"
PROP_FUNNEL_SCHEMA_VERSION = "PROP_FUNNEL_SCHEMA_V1"
PROP_POLICY_VERSION = "PROP_ANALYSIS_POLICY_V1"

PASS = "PASS"
FAIL = "FAIL"
PARTIAL = "PARTIAL"
UNAVAILABLE = "UNAVAILABLE"
PENDING = "PENDING"

STAGES = (
    "GENERATED", "CAUSAL", "BASIC_EDGE", "SHORT_HORIZON_QUALITY",
    "COST_ROBUST", "TEMPORAL_STABLE", "NOVEL", "PORTFOLIO_USEFUL", "PROP_READY",
)

REASONS = {
    "CAUSALITY_FAIL", "INSUFFICIENT_SAMPLE", "NEGATIVE_EXPECTANCY",
    "EDGE_NOT_COST_ROBUST", "SHORT_HORIZON_OPPORTUNITY_LOW",
    "NEGATIVE_TAIL_EXCESSIVE", "LOSS_CLUSTERING_EXCESSIVE",
    "HOLDING_DURATION_EXCESSIVE", "VALIDATION_EDGE_COLLAPSE",
    "VALIDATION_OPPORTUNITY_COLLAPSE", "STRUCTURAL_DUPLICATE",
    "SIGNAL_DUPLICATE", "BEHAVIORAL_NEAR_DUPLICATE", "NOVEL",
    "MISSING_EXECUTION_PROFILE", "MISSING_METRICS", "PENDING_PHASE_D",
    "PENDING_PHASE_E", "ANALYSIS_MODE_GENERAL", "COST_MODEL_PARTIAL",
}


@dataclass(frozen=True)
class FunnelPolicy:
    """Analysis defaults; thresholds are calibration inputs, not approval gates."""

    policy_version: str = PROP_POLICY_VERSION
    min_trade_count: int = 20
    min_mean_R: float = 0.0
    min_positive_window_fraction: float = 0.50
    max_negative_tail_P05: float = -1.50
    max_worst_window_net_R: float = -2.50
    max_holding_P95_hours: float = 240.0
    max_cost_degradation_2x_R: float = -0.50
    validation_edge_ratio_floor: float = 0.25
    validation_opportunity_ratio_floor: float = 0.25
    near_duplicate_distance: float = 0.05
    signal_duplicate_exact: bool = True
    production_approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioMarginalUtilityResult:
    strategy_id: str
    reference_portfolio_set_version: str
    delta_5d_upper_tail: float | None = None
    delta_target_distance: float | None = None
    delta_active_day_coverage: float | None = None
    delta_risk_utilization: float | None = None
    delta_signal_overlap: float | None = None
    delta_downside: float | None = None
    delta_cost_robustness: float | None = None
    evaluation_provenance: str = "UNAVAILABLE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def phase_d_result_schema() -> dict[str, Any]:
    return {"schema_version": "PROP_PHASE_D_UTILITY_SCHEMA_V1", "fields": list(asdict(PortfolioMarginalUtilityResult("id", "version")))}


def phase_e_handoff_schema() -> dict[str, Any]:
    return {
        "schema_version": "PROP_PHASE_E_HANDOFF_SCHEMA_V1",
        "required": ["strategy_id", "PROP_V1_lineage", "funnel_record", "phase_a_metrics_reference", "phase_b_fitness_reference", "phase_d_utility_reference", "economic_spec_reference", "execution_profile_reference", "data_provenance"],
        "PROP_READY_allowed_in_phase_c": False,
    }


def _reason(status: str, reasons: list[str]) -> tuple[str, str]:
    return status, json.dumps(sorted(set(reasons)))


def _metric(row: pd.Series, name: str) -> float | None:
    value = row.get(name)
    return None if value is None or (isinstance(value, float) and not np.isfinite(value)) else float(value)


def _stage_row(sid: str, stage: str, status: str, reasons: list[str], common: Mapping[str, Any], details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = dict(common)
    result.update({"strategy_id": sid, "stage": stage, "status": status, "reason_codes_json": json.dumps(sorted(set(reasons))), "details_json": json.dumps(details or {}, sort_keys=True, default=str)})
    return result


def _timing_signature(row: pd.Series) -> str:
    values = [row.get("hour_histogram_json", ""), row.get("weekday_histogram_json", ""), row.get("local_day_histogram_json", "")]
    return hashlib.sha256("|".join(str(x) for x in values).encode()).hexdigest()


def evaluate_funnel(
    phase_a_metrics: pd.DataFrame,
    phase_b_full: pd.DataFrame,
    phase_b_cheap: pd.DataFrame,
    costs: pd.DataFrame | None = None,
    timing: pd.DataFrame | None = None,
    policy: FunnelPolicy | None = None,
    *,
    lineage: Mapping[str, Any] | None = None,
    mode: str = "ANALYSIS",
    portfolio_utility: Mapping[str, PortfolioMarginalUtilityResult] | None = None,
) -> pd.DataFrame:
    """Return one deterministic record per strategy and funnel stage."""
    policy = policy or FunnelPolicy()
    lineage = dict(lineage or {})
    full = phase_b_full[phase_b_full.split == "DEVELOPMENT"].copy()
    cheap = phase_b_cheap[phase_b_cheap.split == "DEVELOPMENT"].copy()
    primary = phase_a_metrics[(phase_a_metrics.split == "DEVELOPMENT") & (phase_a_metrics.horizon_days == 5)].copy()
    validation = phase_a_metrics[(phase_a_metrics.split == "VALIDATION") & (phase_a_metrics.horizon_days == 5)].copy()
    costs = costs if costs is not None else pd.DataFrame()
    timing_frame = timing if timing is not None else pd.DataFrame()
    timing_map = {str(r.strategy_id): r for _, r in timing_frame.iterrows()}
    seen_timing: dict[tuple[Any, ...], str] = {}
    seen_behavior: dict[tuple[Any, ...], str] = {}
    records: list[dict[str, Any]] = []
    common = {
        "factory_lineage": lineage.get("factory_lineage", "GENERAL"),
        "factory_version": lineage.get("factory_version", "GENERAL_UNKNOWN"),
        "metrics_version": lineage.get("metrics_version", "PROP_METRICS_V1"),
        "fitness_version": lineage.get("fitness_version", "PROP_FITNESS_V1"),
        "funnel_version": PROP_FUNNEL_VERSION,
        "funnel_schema_version": PROP_FUNNEL_SCHEMA_VERSION,
        "policy_version": policy.policy_version,
        "data_provenance_id": lineage.get("data_provenance_id", "UNKNOWN"),
        "execution_profile_id": lineage.get("execution_profile_id", "UNKNOWN"),
        "campaign_id": lineage.get("generation_campaign_id", "ANALYSIS_GENERAL_SAMPLE"),
        "analysis_mode": mode,
    }
    for sid in sorted(set(primary.strategy_id)):
        row = primary[primary.strategy_id == sid].sort_values("horizon_days").iloc[0]
        frow = full[full.strategy_id == sid].iloc[0] if len(full[full.strategy_id == sid]) else pd.Series()
        crow = cheap[cheap.strategy_id == sid].iloc[0] if len(cheap[cheap.strategy_id == sid]) else pd.Series()
        pf = float(frow.profit_factor_R) if len(frow) and pd.notna(frow.profit_factor_R) else None
        common_sid = dict(common)
        common_sid.update({"strategy_id": sid, "execution_profile_id": row.get("execution_profile_id", common["execution_profile_id"])})

        records.append(_stage_row(sid, "GENERATED", PASS, ["ANALYSIS_MODE_GENERAL"] if mode == "ANALYSIS" else [], common_sid, {"canonical_strategy_id": sid}))
        causal_reasons = [] if str(row.get("data_provenance_id", "")).startswith("certified_") else ["CAUSALITY_FAIL"]
        records.append(_stage_row(sid, "CAUSAL", PASS if not causal_reasons else UNAVAILABLE, causal_reasons, common_sid, {"source": row.get("data_provenance_id", "UNKNOWN")}))

        basic_reasons = []
        if len(row) == 0 or int(row.get("trade_count", 0)) < policy.min_trade_count: basic_reasons.append("INSUFFICIENT_SAMPLE")
        if _metric(frow, "edge_mean_R") is not None and _metric(frow, "edge_mean_R") < policy.min_mean_R: basic_reasons.append("NEGATIVE_EXPECTANCY")
        if pf is None: basic_reasons.append("MISSING_METRICS")
        basic_status = FAIL if basic_reasons else PASS
        records.append(_stage_row(sid, "BASIC_EDGE", basic_status, basic_reasons, common_sid, {"profit_factor_R": pf, "mean_R": _metric(frow, "edge_mean_R")}))

        short_reasons = []
        p95 = _metric(frow, "positive_tail_P95"); p05 = _metric(frow, "negative_tail_P05")
        if _metric(frow, "positive_window_fraction") is not None and _metric(frow, "positive_window_fraction") < policy.min_positive_window_fraction: short_reasons.append("SHORT_HORIZON_OPPORTUNITY_LOW")
        if p05 is not None and p05 < policy.max_negative_tail_P05: short_reasons.append("NEGATIVE_TAIL_EXCESSIVE")
        if _metric(frow, "worst_window_net_R") is not None and _metric(frow, "worst_window_net_R") < policy.max_worst_window_net_R: short_reasons.append("NEGATIVE_TAIL_EXCESSIVE")
        if _metric(frow, "holding_P95_hours") is not None and _metric(frow, "holding_P95_hours") > policy.max_holding_P95_hours: short_reasons.append("HOLDING_DURATION_EXCESSIVE")
        records.append(_stage_row(sid, "SHORT_HORIZON_QUALITY", FAIL if short_reasons else PASS, short_reasons, common_sid, {"positive_tail_P95": p95, "negative_tail_P05": p05, "supporting_horizons": [1, 2, 3, 10, 20]}))

        cost_reasons = []
        crows = costs[(costs.strategy_id == sid) & (costs.split == "DEVELOPMENT")] if len(costs) else pd.DataFrame()
        if crows.empty: cost_reasons.append("MISSING_METRICS")
        else:
            one = crows[crows.cost_multiplier == 1.0].net_R
            two = crows[crows.cost_multiplier == 2.0].net_R
            if len(one) and len(two) and float(two.iloc[0] - one.iloc[0]) < policy.max_cost_degradation_2x_R: cost_reasons.append("EDGE_NOT_COST_ROBUST")
        records.append(_stage_row(sid, "COST_ROBUST", FAIL if cost_reasons else PASS, cost_reasons, common_sid, {"cost_status": "PROFILE_MODEL" if not crows.empty else "UNAVAILABLE", "multipliers": [1.0, 1.25, 1.5, 2.0]}))

        vrow = validation[validation.strategy_id == sid]
        temp_reasons = []
        temp_status = PASS
        if vrow.empty: temp_status, temp_reasons = UNAVAILABLE, ["MISSING_METRICS"]
        else:
            dev_edge = _metric(frow, "edge_mean_R") or 0.0; val_edge = _metric(vrow.iloc[0], "mean_R") or 0.0
            dev_opp = _metric(frow, "positive_window_fraction") or 0.0; val_opp = _metric(vrow.iloc[0], "positive_window_fraction") or 0.0
            if dev_edge > 0 and val_edge < dev_edge * policy.validation_edge_ratio_floor: temp_reasons.append("VALIDATION_EDGE_COLLAPSE")
            if dev_opp > 0 and val_opp < dev_opp * policy.validation_opportunity_ratio_floor: temp_reasons.append("VALIDATION_OPPORTUNITY_COLLAPSE")
            temp_status = FAIL if temp_reasons else PASS
        records.append(_stage_row(sid, "TEMPORAL_STABLE", temp_status, temp_reasons, common_sid, {"validation_available": not vrow.empty}))

        novelty_reasons = []
        # Structural identity is unique by canonical ID in this sidecar-only pass.
        signature = _timing_signature(timing_map[sid]) if sid in timing_map else None
        if signature is None: novelty_reasons.append("MISSING_METRICS")
        group_key = (row.get("market"), row.get("timeframe"), row.get("direction"))
        signal_key = group_key + (signature,)
        behavior_values = tuple(round(_metric(frow, name) or 0.0, 6) for name in ("edge_mean_R", "positive_tail_P95", "negative_tail_P05", "active_day_fraction"))
        behavior_key = group_key + behavior_values
        duplicate_type = "NOVEL"
        if signature is not None and signal_key in seen_timing:
            novelty_reasons.append("SIGNAL_DUPLICATE"); duplicate_type = "SIGNAL_DUPLICATE"
        elif behavior_key in seen_behavior:
            novelty_reasons.append("BEHAVIORAL_NEAR_DUPLICATE"); duplicate_type = "BEHAVIORAL_NEAR_DUPLICATE"
        if signature is not None: seen_timing.setdefault(signal_key, sid)
        seen_behavior.setdefault(behavior_key, sid)
        records.append(_stage_row(sid, "NOVEL", PASS if not novelty_reasons else FAIL, novelty_reasons, common_sid, {"timing_signature": signature, "novelty_type": duplicate_type, "novelty_scope": "bounded sample; no Phase D utility"}))
        utility = (portfolio_utility or {}).get(sid)
        utility_status = PASS if utility is not None else PENDING
        utility_reasons = [] if utility is not None else ["PENDING_PHASE_D"]
        records.append(_stage_row(sid, "PORTFOLIO_USEFUL", utility_status, utility_reasons, common_sid, utility.to_dict() if utility else {"contract": "phase_d"}))
        records.append(_stage_row(sid, "PROP_READY", PENDING, ["PENDING_PHASE_D", "PENDING_PHASE_E"], common_sid, {"production_approved": False}))
    return pd.DataFrame(records).sort_values(["strategy_id", "stage"]).reset_index(drop=True)


def deterministic_payload(frame: pd.DataFrame) -> str:
    return frame.sort_values(["strategy_id", "stage"]).to_json()
