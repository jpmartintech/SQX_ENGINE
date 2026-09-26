"""FTMO 2-Step evaluation semantics and deterministic portfolio search helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Ftmo2StepProfile:
    name: str = "FTMO_2STEP_V1"
    initial_capital: float = 1.0
    challenge_target: float = 0.10
    verification_target: float = 0.05
    daily_loss_fraction: float = 0.05
    maximum_loss_fraction: float = 0.10
    minimum_trading_days: int = 4
    trading_period: str = "UNLIMITED"
    timezone: str = "Europe/Paris"

    @property
    def maximum_loss_limit(self) -> float:
        return self.initial_capital * (1.0 - self.maximum_loss_fraction)

    def to_dict(self):
        d = asdict(self)
        d["daily_loss_amount"] = self.initial_capital * self.daily_loss_fraction
        d["maximum_loss_limit"] = self.maximum_loss_limit
        return d


def _local_day(ts, timezone: str) -> str:
    value = pd.Timestamp(ts)
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    return str(value.tz_convert(ZoneInfo(timezone)).date())


def _trade_event_frame(events) -> pd.DataFrame:
    if isinstance(events, pd.DataFrame):
        out = events.copy()
    else:
        out = pd.DataFrame(events)
    if out.empty:
        return pd.DataFrame(columns=["entry_time", "exit_time", "net_return"])
    for c in ("entry_time", "exit_time"):
        out[c] = pd.to_datetime(out[c], utc=True)
    out["net_return"] = out["net_return"].astype(float)
    return out.sort_values(["exit_time", "entry_time"]).reset_index(drop=True)


class Ftmo2StepSimulator:
    """Causal FTMO evaluator.

    Events are closed-trade PnL plus entry/exit timestamps.  If an ``equity``
    column is supplied it is used as an MTM observation; otherwise the result
    is explicitly marked ``CLOSED_TRADE_PROXY`` and is not exact FTMO equity
    certification.
    """
    def __init__(self, profile: Ftmo2StepProfile = Ftmo2StepProfile()):
        self.profile = profile

    def run(self, events, target: float | None = None, risk_fraction: float = 0.01):
        frame = _trade_event_frame(events)
        target = self.profile.challenge_target if target is None else float(target)
        if frame.empty:
            return {"status": "RIGHT_CENSORED", "days": 0, "trades": 0, "trading_days": 0, "mode": "CLOSED_TRADE_PROXY"}
        frame["scaled_pnl"] = frame.net_return * float(risk_fraction / 0.01) * self.profile.initial_capital
        frame["entry_day"] = frame.entry_time.map(lambda x: _local_day(x, self.profile.timezone))
        frame["exit_day"] = frame.exit_time.map(lambda x: _local_day(x, self.profile.timezone))
        entry_order = np.sort(frame.entry_time.to_numpy(dtype="datetime64[ns]"))
        exit_order = np.sort(frame.exit_time.to_numpy(dtype="datetime64[ns]"))
        balance = self.profile.initial_capital
        trading_days: set[str] = set()
        midnight_balance = {}
        current_day = None
        max_dd = 0.0
        peak = balance
        daily_loss_min = 0.0
        for i, row in frame.iterrows():
            day = row.exit_day
            if day != current_day:
                current_day = day
                midnight_balance[day] = balance
            trading_days.add(row.entry_day)
            # Closed-trade replay can enforce realized losses.  Floating MTM is
            # injected when available by callers; absent it is conservative only
            # for closed paths and remains explicitly non-exact.
            balance += float(row.scaled_pnl)
            peak = max(peak, balance)
            max_dd = max(max_dd, (peak - balance) / self.profile.initial_capital)
            day_limit = midnight_balance[day] - self.profile.daily_loss_fraction * self.profile.initial_capital
            daily_loss_min = min(daily_loss_min, (balance - midnight_balance[day]) / self.profile.initial_capital)
            if balance < self.profile.maximum_loss_limit:
                return self._result("MAX_LOSS_FAIL", i + 1, balance, trading_days, max_dd, daily_loss_min, target, row.exit_time, frame.entry_time.min())
            if balance < day_limit:
                return self._result("DAILY_LOSS_FAIL", i + 1, balance, trading_days, max_dd, daily_loss_min, target, row.exit_time, frame.entry_time.min())
            # A target reached while another position remains open is not a
            # pass.  The replay stream contains closed trades, so determine
            # whether any position from the episode is still open at this
            # causal exit event.
            event_time = np.datetime64(row.exit_time.to_datetime64())
            open_after = int(np.searchsorted(entry_order, event_time, side="right") - np.searchsorted(exit_order, event_time, side="right"))
            if balance >= self.profile.initial_capital * (1 + target) and len(trading_days) >= self.profile.minimum_trading_days and open_after == 0:
                return self._result("PASS", i + 1, balance, trading_days, max_dd, daily_loss_min, target, row.exit_time, frame.entry_time.min())
        return self._result("RIGHT_CENSORED", len(frame), balance, trading_days, max_dd, daily_loss_min, target, frame.exit_time.max(), frame.entry_time.min())

    def _result(self, status, trades, balance, trading_days, max_dd, daily_loss_min, target, pass_time=None, start_time=None):
        elapsed_days = 0 if start_time is None or pass_time is None else max(0, int((pass_time - start_time).total_seconds() / 86400))
        return {"status": status, "trades": int(trades), "days": elapsed_days, "trading_days": len(trading_days), "final_balance": float(balance), "return": float(balance / self.profile.initial_capital - 1), "max_drawdown": float(max_dd), "min_equity": float(balance), "min_daily_return": float(daily_loss_min), "target": float(target), "pass_time": pass_time, "mode": "CLOSED_TRADE_PROXY", "equity_mtm_exact": False}


def canonical_portfolio_hash(strategy_ids, weights, risk_policy, risk_fraction, max_open_risk, weighting_mode):
    payload = {"strategy_ids": sorted(strategy_ids), "weights": {k: float(weights[k]) for k in sorted(weights)}, "risk_policy": risk_policy, "risk_fraction": float(risk_fraction), "max_open_risk": float(max_open_risk), "weighting_mode": weighting_mode, "profile": "FTMO_2STEP_V1"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def normalize_weights(strategy_ids, mode="EQUAL_RISK", volatilities=None, max_single_fraction=0.20):
    ids = list(strategy_ids)
    if not ids:
        raise ValueError("portfolio must contain strategies")
    if mode == "EQUAL_RISK" and volatilities:
        raw = np.array([1.0 / max(float(volatilities.get(x, 1.0)), 1e-12) for x in ids])
    else:
        raw = np.ones(len(ids), dtype=float)
    raw = raw / raw.sum()
    cap = float(max_single_fraction)
    if cap * len(ids) < 1.0:
        raise ValueError("concentration cap infeasible for portfolio size")
    # Capped proportional water-fill.  Recomputing the proposal from the
    # remaining mass avoids the common error of redistributing excess into a
    # component that is itself already above the concentration cap.
    remaining = 1.0
    active = np.ones(len(ids), dtype=bool)
    result = np.zeros(len(ids), dtype=float)
    while active.any():
        proposal = remaining * raw[active] / max(raw[active].sum(), 1e-12)
        active_idx = np.flatnonzero(active)
        violating = proposal > cap + 1e-15
        if not violating.any():
            result[active_idx] = proposal
            break
        capped_idx = active_idx[violating]
        result[capped_idx] = cap
        remaining -= cap * len(capped_idx)
        active[capped_idx] = False
    result /= result.sum()
    raw = result
    return dict(zip(ids, raw.tolist()))
