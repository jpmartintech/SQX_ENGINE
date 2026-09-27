"""Deterministic strategy-level short-horizon metrics for Phase A.

These metrics describe normalized strategy economics. They do not convert R
to account return: risk allocation remains a Portfolio Factory concern.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json
from typing import Iterable, Sequence
import numpy as np
import pandas as pd

HORIZONS = (1, 2, 3, 5, 10, 20)
COST_MULTIPLIERS = (1.0, 1.25, 1.5, 2.0)
LOCAL_TZ = "Europe/Paris"


def _q(values: pd.Series | np.ndarray, q: float) -> float:
    x = pd.Series(values, dtype=float).dropna()
    return float(x.quantile(q)) if len(x) else 0.0


def _distribution(values: pd.Series | np.ndarray) -> dict[str, float]:
    x = pd.Series(values, dtype=float).dropna()
    return {"P01": _q(x, .01), "P05": _q(x, .05), "P10": _q(x, .10), "P25": _q(x, .25),
            "P50": _q(x, .50), "P75": _q(x, .75), "P90": _q(x, .90), "P95": _q(x, .95),
            "P99": _q(x, .99), "MIN": float(x.min()) if len(x) else 0.0,
            "MAX": float(x.max()) if len(x) else 0.0}


def _split_bounds(frame: pd.DataFrame) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    local = frame.entry_timestamp.dt.tz_convert(LOCAL_TZ).dt.normalize()
    first, last = local.min().normalize(), (local.max() + pd.Timedelta(days=1)).normalize()
    total_days = (last - first).days
    # Split boundaries are local-midnight timestamps, never fractional days.
    a = first + pd.Timedelta(days=max(1, int(total_days * .60)))
    b = first + pd.Timedelta(days=max(2, int(total_days * .80)))
    return {"DEVELOPMENT": (first, a), "VALIDATION": (a, b), "OOS": (b, last)}


def _window_rows(x: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, horizon: int) -> pd.DataFrame:
    """Calendar windows via daily aggregates and cumulative sums.

    The resulting interval is exactly [window_start, window_end), while the
    daily aggregation avoids repeatedly filtering a strategy's trade frame.
    """
    days = pd.date_range(start, end - pd.Timedelta(days=horizon), freq="D", tz=LOCAL_TZ)
    calendar = pd.date_range(start, end - pd.Timedelta(days=1), freq="D", tz=LOCAL_TZ)
    # Precompute sign partitions so the per-strategy rolling aggregation uses
    # native groupby reductions rather than Python callbacks. Values and
    # window semantics are unchanged.
    work = x[["local_day", "net_R"]].copy()
    work["positive_R"] = work.net_R.clip(lower=0.0)
    work["negative_R"] = work.net_R.clip(upper=0.0)
    work["positive_winners"] = (work.net_R > 0).astype(float)
    daily = work.groupby("local_day", sort=True).agg(
        trade_count=("net_R", "size"), net_R=("net_R", "sum"),
        positive_R=("positive_R", "sum"), negative_R=("negative_R", "sum"),
        positive_winners=("positive_winners", "sum"),
    ).reindex(calendar, fill_value=0.0)
    values = {}
    for column in ("trade_count", "net_R", "positive_R", "negative_R", "positive_winners"):
        arr = daily[column].to_numpy(dtype=float)
        cumulative = np.concatenate(([0.0], np.cumsum(arr)))
        values[column] = cumulative[horizon:] - cumulative[:-horizon]
    active = (daily.trade_count.to_numpy(dtype=float) > 0).astype(float)
    cumulative_active = np.concatenate(([0.0], np.cumsum(active)))
    values["active_days"] = cumulative_active[horizon:] - cumulative_active[:-horizon]
    result = pd.DataFrame({"window_start": calendar[:len(values["net_R"])], **values})
    result = result[result.window_start.isin(days)].copy()
    result["window_end"] = result.window_start + pd.Timedelta(days=horizon)
    return result.reset_index(drop=True)


def _longest_run(values: Iterable[bool]) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return int(best)


def _metric_row(sid: str, x: pd.DataFrame, split: str, horizon: int, provenance: str, execution_profile: str) -> dict:
    w = _window_rows(x, x.split_start.iloc[0], x.split_end.iloc[0], horizon)
    counts = w.trade_count if len(w) else pd.Series(dtype=float)
    active = w.active_days if len(w) else pd.Series(dtype=float)
    intervals = x.entry_timestamp.sort_values().diff().dt.total_seconds().div(86400).dropna()
    durations = (x.exit_timestamp - x.entry_timestamp).dt.total_seconds().div(3600).clip(lower=0)
    positive = w.net_R > 0 if len(w) else pd.Series(dtype=bool)
    negative = w.net_R < 0 if len(w) else pd.Series(dtype=bool)
    row = {"strategy_id": sid, "split": split, "horizon_days": horizon, "window_count": len(w),
           "trade_count": len(x), "signals_per_day": float(len(x) / max((x.split_end.iloc[0] - x.split_start.iloc[0]).days, 1)),
           "signals_per_window": float(counts.mean()) if len(counts) else 0.0,
           "active_day_fraction": float(active.gt(0).mean()) if len(active) else 0.0,
           "median_time_between_signals_days": float(intervals.median()) if len(intervals) else None,
           "P90_time_between_signals_days": float(intervals.quantile(.90)) if len(intervals) else None,
           "window_0_fraction": float((counts == 0).mean()) if len(counts) else 1.0,
           "window_ge_1_fraction": float((counts >= 1).mean()) if len(counts) else 0.0,
           "window_ge_2_fraction": float((counts >= 2).mean()) if len(counts) else 0.0,
           "window_ge_3_fraction": float((counts >= 3).mean()) if len(counts) else 0.0,
           "window_ge_5_fraction": float((counts >= 5).mean()) if len(counts) else 0.0,
           "active_days_P50": _q(active, .5), "active_days_P95": _q(active, .95),
           "active_days_ge_1_fraction": float((active >= 1).mean()) if len(active) else 0.0,
           "active_days_ge_2_fraction": float((active >= 2).mean()) if len(active) else 0.0,
           "active_days_ge_3_fraction": float((active >= 3).mean()) if len(active) else 0.0,
           "active_days_ge_4_fraction": float((active >= 4).mean()) if len(active) else 0.0,
           "active_days_ge_5_fraction": float((active >= 5).mean()) if len(active) else 0.0,
           "positive_window_fraction": float(positive.mean()) if len(positive) else 0.0,
           "negative_window_fraction": float(negative.mean()) if len(negative) else 0.0,
           "flat_window_fraction": float((w.net_R == 0).mean()) if len(w) else 1.0,
           "mean_R": float(x.net_R.mean()) if len(x) else 0.0,
           "median_R": float(x.net_R.median()) if len(x) else 0.0,
           "net_R_total": float(x.net_R.sum()) if len(x) else 0.0,
           "net_R_distribution_json": json.dumps(_distribution(w.net_R if len(w) else []), sort_keys=True),
           "positive_tail_json": json.dumps({k: _q(w.net_R[w.net_R > 0], q) for k, q in {"P75": .75, "P90": .90, "P95": .95, "P99": .99}.items()}, sort_keys=True),
           "negative_tail_json": json.dumps({k: _q(w.net_R, q) for k, q in {"P01": .01, "P05": .05, "P10": .10}.items()}, sort_keys=True),
           "worst_window_net_R": float(w.net_R.min()) if len(w) else 0.0,
           "maximum_consecutive_negative_windows": _longest_run(negative.tolist()),
           "holding_P25_hours": _q(durations, .25), "holding_P50_hours": _q(durations, .50),
           "holding_P75_hours": _q(durations, .75), "holding_P90_hours": _q(durations, .90),
           "holding_P95_hours": _q(durations, .95), "holding_MAX_hours": _q(durations, 1.0),
           "closed_within_24h_fraction": float((durations <= 24).mean()) if len(durations) else 0.0,
           "closed_within_48h_fraction": float((durations <= 48).mean()) if len(durations) else 0.0,
           "closed_within_5d_fraction": float((durations <= 120).mean()) if len(durations) else 0.0,
           "market": str(x.market.iloc[0]) if len(x) else "UNKNOWN", "timeframe": str(x.timeframe.iloc[0]) if len(x) else "UNKNOWN",
           "direction": str(x.direction.iloc[0]) if len(x) and x.direction.nunique() == 1 else "MIXED",
           "data_provenance_id": provenance, "execution_profile_id": execution_profile, "metrics_version": "PROP_METRICS_V1"}
    return row


@dataclass(frozen=True)
class ShortHorizonOpportunityVector:
    strategy_id: str
    horizon_days: int
    frequency: float
    active_coverage: float
    net_R: float
    positive_tail: dict
    negative_tail: dict
    duration_hours_P50: float
    loss_cluster_length: int
    cost_sensitivity: str = "PROFILE_MODEL"
    metrics_version: str = "PROP_METRICS_V1"

    def to_dict(self):
        return asdict(self)


def select_validation_sample(geometry: pd.DataFrame, n: int = 200) -> pd.DataFrame:
    """Deterministically stratify by market/timeframe/direction/frequency/holding."""
    x = geometry.copy(); x["entry_timestamp"] = pd.to_datetime(x.entry_timestamp, utc=True)
    x["hold_hours"] = (pd.to_datetime(x.exit_timestamp, utc=True) - x.entry_timestamp).dt.total_seconds() / 3600
    meta = x.groupby("strategy_id").agg(market=("market", "first"), timeframe=("timeframe", "first"), direction=("direction", "first"), trades=("strategy_id", "size"), hold=("hold_hours", "median")).reset_index()
    meta["freq_bin"] = pd.qcut(meta.trades.rank(method="first"), 3, labels=False)
    meta["hold_bin"] = pd.qcut(meta.hold.rank(method="first"), 3, labels=False)
    meta["key"] = meta.strategy_id.map(lambda s: hashlib.sha256(s.encode()).hexdigest())
    meta = meta.sort_values("key")
    selected = []
    groups = [g for _, g in meta.groupby(["market", "timeframe", "direction", "freq_bin", "hold_bin"], sort=True)]
    cursor = 0
    while len(selected) < min(n, len(meta)):
        group = groups[cursor % len(groups)]
        if len(group):
            sid = group.iloc[0].strategy_id
            if sid not in selected: selected.append(sid)
            groups[cursor % len(groups)] = group.iloc[1:]
        cursor += 1
        if cursor > len(meta) * 4: break
    return meta[meta.strategy_id.isin(selected)].sort_values("strategy_id").reset_index(drop=True)


def compute_prop_metrics(geometry: pd.DataFrame, strategy_ids: Sequence[str] | None = None, provenance_id: str = "GEOMETRY_LEDGER", execution_profile_by_market_tf: dict | None = None) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Compute sidecar metrics; no library rows are mutated."""
    g = geometry.copy(); g["entry_timestamp"] = pd.to_datetime(g.entry_timestamp, utc=True); g["exit_timestamp"] = pd.to_datetime(g.exit_timestamp, utc=True)
    g["local_day"] = g.entry_timestamp.dt.tz_convert(LOCAL_TZ).dt.normalize()
    if strategy_ids is not None: g = g[g.strategy_id.isin(strategy_ids)].copy()
    bounds = _split_bounds(g); rows = []
    for sid, raw in g.groupby("strategy_id", sort=True):
        for split, (start, end) in bounds.items():
            x = raw[(raw.local_day >= start) & (raw.local_day < end)].copy(); x["split_start"] = start; x["split_end"] = end
            profile = (execution_profile_by_market_tf or {}).get((str(x.market.iloc[0]), str(x.timeframe.iloc[0])), "UNKNOWN") if len(x) else "UNKNOWN"
            for horizon in HORIZONS:
                if len(x) and (end - start).days >= horizon: rows.append(_metric_row(sid, x, split, horizon, provenance_id, profile))
    metrics = pd.DataFrame(rows)
    cost_rows = []
    for sid, x in g.groupby("strategy_id", sort=True):
        for split, (start, end) in bounds.items():
            z = x[(x.local_day >= start) & (x.local_day < end)].copy()
            if not len(z): continue
            cost_base = z.get("gross_R", z.net_R) - z.net_R
            profile = (execution_profile_by_market_tf or {}).get(
                (str(z.market.iloc[0]), str(z.timeframe.iloc[0])), "UNKNOWN"
            )
            for multiplier in COST_MULTIPLIERS:
                nr = z.net_R - cost_base * (multiplier - 1.0)
                cost_rows.append({"strategy_id": sid, "split": split,
                                  "cost_multiplier": multiplier,
                                  "cost_status": "PROFILE_MODEL",
                                  "net_R": float(nr.sum()),
                                  "expectancy_R": float(nr.mean()),
                                  "positive_window_fraction": float((nr > 0).mean()),
                                  "market": str(z.market.iloc[0]),
                                  "timeframe": str(z.timeframe.iloc[0]),
                                  "data_provenance_id": provenance_id,
                                  "execution_profile_id": profile,
                                  "metrics_version": "PROP_METRICS_V1"})
    costs = pd.DataFrame(cost_rows)
    return metrics, {"cost_sensitivity": costs}
