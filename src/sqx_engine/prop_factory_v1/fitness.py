"""Phase B PROP fitness adapters.

The adapter consumes Phase A sidecars and returns structured objective
vectors.  It deliberately never converts strategy R into account return and
never runs portfolio or equity replay.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from typing import Any, Mapping

import numpy as np
import pandas as pd

PROP_FITNESS_VERSION = "PROP_FITNESS_V1"
PROP_FITNESS_SCHEMA_VERSION = "PROP_FITNESS_SCHEMA_V1"
MISSING = "UNAVAILABLE"
INSUFFICIENT = "INSUFFICIENT_SAMPLE"

# Positive means economically better.  Negative means economically worse.
OBJECTIVE_DIRECTIONS = {
    "edge_mean_R": 1,
    "edge_median_R": 1,
    "profit_factor_R": 1,
    "positive_window_fraction": 1,
    "positive_tail_P95": 1,
    "positive_tail_P99": 1,
    "active_day_fraction": 1,
    "signals_per_day": 1,
    "negative_tail_P01": -1,
    "negative_tail_P05": -1,
    "worst_window_net_R": -1,
    "maximum_consecutive_negative_windows": -1,
    "holding_P50_hours": -1,
    "holding_P95_hours": -1,
    "cost_degradation_2x_R": -1,
    "cost_adjusted_net_R_2x": 1,
}

CHEAP_OBJECTIVES = (
    "edge_mean_R", "edge_median_R", "profit_factor_R", "signals_per_day", "active_day_fraction",
    "positive_window_fraction", "negative_tail_P05", "worst_window_net_R",
    "holding_P50_hours", "maximum_consecutive_negative_windows",
)
FULL_OBJECTIVES = tuple(OBJECTIVE_DIRECTIONS)


@dataclass(frozen=True)
class FitnessValue:
    value: float | None
    status: str = "AVAILABLE"
    source: str = "phase_a_sidecar"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PropFitnessVector:
    strategy_id: str
    level: str
    split: str
    horizon_days: int
    objectives: dict[str, FitnessValue]
    metrics_version: str
    fitness_version: str = PROP_FITNESS_VERSION
    fitness_schema_version: str = PROP_FITNESS_SCHEMA_VERSION
    data_provenance_id: str = "UNKNOWN"
    execution_profile_id: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["objectives"] = {k: v.to_dict() for k, v in self.objectives.items()}
        return result


def _json_tail(row: pd.Series, column: str, key: str) -> float | None:
    value = row.get(column)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        result = parsed.get(key)
        return None if result is None else float(result)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _value(value: Any, source: str = "phase_a_sidecar") -> FitnessValue:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return FitnessValue(None, MISSING, source)
    return FitnessValue(float(value), "AVAILABLE", source)


def _row_to_objectives(row: pd.Series, level: str, cost_row: pd.Series | None = None,
                       profit_factor: float | None = None) -> dict[str, FitnessValue]:
    values: dict[str, FitnessValue] = {
        "edge_mean_R": _value(row.get("mean_R")),
        "edge_median_R": _value(row.get("median_R")),
        "positive_window_fraction": _value(row.get("positive_window_fraction")),
        "positive_tail_P95": _value(_json_tail(row, "positive_tail_json", "P95")),
        "positive_tail_P99": _value(_json_tail(row, "positive_tail_json", "P99")),
        "active_day_fraction": _value(row.get("active_day_fraction")),
        "signals_per_day": _value(row.get("signals_per_day")),
        "negative_tail_P01": _value(_json_tail(row, "negative_tail_json", "P01")),
        "negative_tail_P05": _value(_json_tail(row, "negative_tail_json", "P05")),
        "worst_window_net_R": _value(row.get("worst_window_net_R")),
        "maximum_consecutive_negative_windows": _value(row.get("maximum_consecutive_negative_windows")),
        "holding_P50_hours": _value(row.get("holding_P50_hours")),
        "holding_P95_hours": _value(row.get("holding_P95_hours")),
    }
    # Phase A deliberately does not invent gross profit-factor data.  A future
    # ledger extension may provide it; until then the missing state is explicit.
    values["profit_factor_R"] = _value(
        row.get("profit_factor_R") if profit_factor is None else profit_factor,
        "phase_a_sidecar" if profit_factor is None else "certified_trade_ledger",
    )
    if cost_row is None:
        values["cost_degradation_2x_R"] = FitnessValue(None, MISSING, "cost_sensitivity_sidecar")
        values["cost_adjusted_net_R_2x"] = FitnessValue(None, MISSING, "cost_sensitivity_sidecar")
    else:
        values["cost_degradation_2x_R"] = _value(cost_row.get("cost_degradation_2x_R"), "cost_sensitivity_sidecar")
        values["cost_adjusted_net_R_2x"] = _value(cost_row.get("cost_adjusted_net_R_2x"), "cost_sensitivity_sidecar")
    for multiplier in ("1x", "1_25x", "1_5x", "2x"):
        key = f"cost_adjusted_net_R_{multiplier}"
        if key not in values:
            values[key] = _value(cost_row.get(key) if cost_row is not None else None, "cost_sensitivity_sidecar")
    return values


def _base_frame(metrics: pd.DataFrame, costs: pd.DataFrame | None, *, level: str,
                horizon_days: int, split: str,
                profit_factor_by_strategy_split: Mapping[tuple[str, str], float] | None = None) -> pd.DataFrame:
    required = {"strategy_id", "horizon_days", "split"}
    missing = required - set(metrics.columns)
    if missing:
        raise ValueError(f"Phase A metrics missing required columns: {sorted(missing)}")
    rows = metrics[(metrics.horizon_days == horizon_days) & (metrics.split == split)].copy()
    if rows.empty:
        return pd.DataFrame()
    cost_map: dict[str, pd.Series] = {}
    if costs is not None and not costs.empty:
        c = costs[costs.split == split].copy()
        for sid, group in c.groupby("strategy_id", sort=True):
            one = group.sort_values("cost_multiplier")
            base = one[one.cost_multiplier == 1.0].net_R
            high = one[one.cost_multiplier == 2.0].net_R
            if len(base) and len(high):
                values = {
                    "cost_degradation_2x_R": float(high.iloc[0] - base.iloc[0]),
                    "cost_adjusted_net_R_2x": float(high.iloc[0]),
                }
                for multiplier, label in ((1.0, "1x"), (1.25, "1_25x"), (1.5, "1_5x"), (2.0, "2x")):
                    selected = one[one.cost_multiplier == multiplier].net_R
                    if len(selected):
                        values[f"cost_adjusted_net_R_{label}"] = float(selected.iloc[0])
                cost_map[sid] = pd.Series(values)
    output: list[dict[str, Any]] = []
    for _, row in rows.sort_values("strategy_id").iterrows():
        sid = str(row.strategy_id)
        cv = cost_map.get(sid)
        pf = (profit_factor_by_strategy_split or {}).get((sid, split))
        objectives = _row_to_objectives(row, level, cv, pf)
        item = {
            "strategy_id": sid,
            "level": level,
            "split": split,
            "horizon_days": horizon_days,
            "metrics_version": str(row.get("metrics_version", "UNKNOWN")),
            "data_provenance_id": str(row.get("data_provenance_id", "UNKNOWN")),
            "execution_profile_id": str(row.get("execution_profile_id", "UNKNOWN")),
            "missing_objectives_json": json.dumps(sorted(k for k, v in objectives.items() if v.status != "AVAILABLE")),
        }
        item.update({name: value.value for name, value in objectives.items()})
        item.update({f"{name}__status": value.status for name, value in objectives.items()})
        # Retain the complete authoritative Phase A row alongside the
        # objective vector.  This keeps FULL sidecars auditable and prevents
        # downstream funnel stages from silently losing distribution fields.
        for name, value in row.items():
            if name not in item and not str(name).endswith("__status"):
                item[name] = value
        output.append(item)
    return pd.DataFrame(output)


def evaluate_cheap(candidate_statistics: pd.DataFrame, *, horizon_days: int = 5,
                   split: str = "DEVELOPMENT") -> pd.DataFrame:
    """Return inexpensive individual vectors from Phase A rows.

    No replay is performed.  Missing fields remain null with an explicit
    ``__status`` column rather than becoming a favorable default.
    """
    result = _base_frame(candidate_statistics, None, level="CHEAP", horizon_days=horizon_days, split=split)
    if result.empty:
        return result
    keep = ["strategy_id", "level", "split", "horizon_days", "metrics_version", "data_provenance_id", "execution_profile_id", "missing_objectives_json"]
    keep += [x for x in CHEAP_OBJECTIVES if x in result]
    keep += [f"{x}__status" for x in CHEAP_OBJECTIVES if f"{x}__status" in result]
    return result[keep].sort_values("strategy_id").reset_index(drop=True)


def evaluate_full(metrics: pd.DataFrame, costs: pd.DataFrame | None = None, *,
                  horizon_days: int = 5, split: str = "DEVELOPMENT",
                  profit_factor_by_strategy_split: Mapping[tuple[str, str], float] | None = None) -> pd.DataFrame:
    """Return the complete Phase A-derived vector for one horizon/split."""
    result = _base_frame(metrics, costs, level="FULL", horizon_days=horizon_days, split=split,
                         profit_factor_by_strategy_split=profit_factor_by_strategy_split)
    return result.sort_values("strategy_id").reset_index(drop=True) if not result.empty else result


def _objective_columns(frame: pd.DataFrame) -> list[str]:
    return [name for name in OBJECTIVE_DIRECTIONS if name in frame.columns]


def normalize_objectives(frame: pd.DataFrame, objectives: tuple[str, ...] = FULL_OBJECTIVES) -> pd.DataFrame:
    """Normalize available objectives to [0,1]; unavailable values stay null."""
    result = frame.copy()
    for name in objectives:
        if name not in result:
            continue
        values = pd.to_numeric(result[name], errors="coerce")
        valid = values.dropna()
        if valid.empty:
            result[f"{name}__normalized"] = np.nan
            continue
        lo, hi = float(valid.min()), float(valid.max())
        normalized = pd.Series(np.nan, index=result.index, dtype=float)
        if hi == lo:
            normalized.loc[values.notna()] = 1.0
        else:
            normalized.loc[values.notna()] = (values[values.notna()] - lo) / (hi - lo)
        if OBJECTIVE_DIRECTIONS.get(name, 1) < 0:
            normalized = 1.0 - normalized
        result[f"{name}__normalized"] = normalized
    return result


def dominates(a: Mapping[str, Any] | pd.Series, b: Mapping[str, Any] | pd.Series,
              objectives: tuple[str, ...] = FULL_OBJECTIVES) -> bool:
    """Deterministic Pareto dominance, ignoring unavailable dimensions."""
    comparable = []
    strictly_better = False
    for name in objectives:
        av, bv = a.get(name), b.get(name)
        if av is None or bv is None or not np.isfinite(av) or not np.isfinite(bv):
            continue
        comparable.append(name)
        direction = OBJECTIVE_DIRECTIONS.get(name, 1)
        if direction > 0:
            if av < bv:
                return False
            strictly_better |= av > bv
        else:
            if av > bv:
                return False
            strictly_better |= av < bv
    return bool(comparable) and strictly_better


def pareto_rank(frame: pd.DataFrame, objectives: tuple[str, ...] = FULL_OBJECTIVES) -> pd.DataFrame:
    """Assign front 0, 1, ... using stable strategy-ID tie-breaking."""
    if frame.empty:
        return frame.assign(pareto_front=pd.Series(dtype=int), pareto_rank_status=pd.Series(dtype=str))
    work = frame.sort_values("strategy_id").reset_index(drop=True).copy()
    remaining = list(range(len(work)))
    fronts: list[int] = []
    rank = np.full(len(work), -1, dtype=int)
    front_no = 0
    while remaining:
        front = []
        for i in remaining:
            if not any(dominates(work.iloc[j], work.iloc[i], objectives) for j in remaining if j != i):
                front.append(i)
        if not front:
            front = [remaining[0]]
        for i in front:
            rank[i] = front_no
        remaining = [i for i in remaining if i not in set(front)]
        front_no += 1
    work["pareto_front"] = rank
    work["pareto_rank_status"] = "AVAILABLE"
    return work


def fitness_vector(frame: pd.DataFrame, strategy_id: str) -> PropFitnessVector:
    row = frame[frame.strategy_id == strategy_id].sort_values("strategy_id").iloc[0]
    objectives = {}
    for name in OBJECTIVE_DIRECTIONS:
        status = row.get(f"{name}__status", "AVAILABLE" if pd.notna(row.get(name)) else MISSING)
        value = row.get(name)
        objectives[name] = FitnessValue(None if pd.isna(value) else float(value), str(status))
    return PropFitnessVector(
        strategy_id=strategy_id, level=str(row.level), split=str(row.split),
        horizon_days=int(row.horizon_days), objectives=objectives,
        metrics_version=str(row.metrics_version),
        data_provenance_id=str(row.data_provenance_id),
        execution_profile_id=str(row.execution_profile_id),
    )
