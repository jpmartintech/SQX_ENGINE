"""Causal contracts for rolling recent-edge experiments."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
import pandas as pd


@dataclass(frozen=True)
class RollingCycle:
    forward_year: int
    manufacture_start: date
    manufacture_end: date
    forward_start: date
    forward_end: date
    partial_forward: bool = False

    def to_dict(self):
        return asdict(self)


def rolling_cycles(data_start, data_end, lookback_years=5, forward_years=1,
                   step_years=1, include_partial=False):
    """Return complete calendar manufacture→Forward cycles only.

    The forward interval is half-open: [Jan 1, Jan 1 of the next year).
    Partial final years are explicitly labeled and never included by default.
    """
    start = data_start if isinstance(data_start, date) and not isinstance(data_start, pd.Timestamp) else pd.Timestamp(data_start).date()
    end = data_end if isinstance(data_end, date) and not isinstance(data_end, pd.Timestamp) else pd.Timestamp(data_end).date()
    first_forward = start.year + lookback_years
    out = []
    for year in range(first_forward, end.year + 1, step_years):
        m_start = date(year - lookback_years, 1, 1)
        m_end = date(year, 1, 1)
        f_start = date(year, 1, 1)
        f_end = date(year + forward_years, 1, 1)
        partial = end < f_end
        if m_start >= start and m_end <= end and (f_end <= end or include_partial):
            out.append(RollingCycle(year, m_start, m_end, f_start, f_end, partial))
    return out


def assert_forward_firewall(manufacture_end, forward_start, accessed_timestamps=()):
    """Reject any manufacturing/search access at or after Forward start."""
    mend = pd.Timestamp(manufacture_end, tz="UTC") if pd.Timestamp(manufacture_end).tzinfo is None else pd.Timestamp(manufacture_end).tz_convert("UTC")
    fstart = pd.Timestamp(forward_start, tz="UTC") if pd.Timestamp(forward_start).tzinfo is None else pd.Timestamp(forward_start).tz_convert("UTC")
    if mend > fstart:
        raise ValueError("manufacturing window overlaps Forward")
    accessed = pd.to_datetime(list(accessed_timestamps), utc=True)
    if len(accessed) and (accessed >= fstart).any():
        raise ValueError("Forward data accessed before portfolio freeze")
    return True


def strategy_gate(net_pf, completed_trades, causality=True, economics=True,
                  execution_profile=True):
    return {
        "net_pf": float(net_pf), "completed_trades": int(completed_trades),
        "causality": bool(causality), "economic_reconstruction": bool(economics),
        "execution_profile": bool(execution_profile),
        "pass": bool(float(net_pf) > 1.15 and int(completed_trades) > 250 and causality and economics and execution_profile),
    }


def activity_metrics(equity, equity_timestamps, trade_timestamps=()):
    """Descriptive high-water stagnation and completed-trade gap metrics."""
    eq = pd.Series(equity, index=pd.to_datetime(equity_timestamps, utc=True)).sort_index()
    high = eq.cummax(); new_high = eq > high.shift(1).fillna(float("-inf")); highs = eq.index[new_high]
    stagnation = pd.Series(highs).diff().dropna().dt.total_seconds() / 86400 if len(highs) else pd.Series(dtype=float)
    trades = pd.Series(pd.to_datetime(list(trade_timestamps), utc=True)).sort_values().diff().dropna().dt.total_seconds() / 86400
    q = lambda s, p: float(s.quantile(p)) if len(s) else None
    return {"median_equity_stagnation_days": q(stagnation,.5), "p90_equity_stagnation_days": q(stagnation,.9), "max_equity_stagnation_days": float(stagnation.max()) if len(stagnation) else None,
            "median_trade_gap_days": q(trades,.5), "p90_trade_gap_days": q(trades,.9), "max_trade_gap_days": float(trades.max()) if len(trades) else None}
