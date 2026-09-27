"""Versioned current FTMO profiles and bounded exact normalized replay.

This module is additive.  The historical FTMO V1/V2 simulators remain
unchanged for reproducibility.  Positions are supplied with explicit geometry
and normalized ``net_R``; one R is scaled by the portfolio's allocated risk.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from .ftmo_v2 import _local_day


FTMO_1STEP_CURRENT_V1 = "FTMO_1STEP_CURRENT_V1"
FTMO_2STEP_CURRENT_V1 = "FTMO_2STEP_CURRENT_V1"


@dataclass(frozen=True)
class FtmoCurrentProfile:
    name: str
    initial_capital: float = 1.0
    target: float = 0.10
    daily_loss_fraction: float = 0.05
    maximum_loss_fraction: float = 0.10
    minimum_trading_days: int = 0
    timezone: str = "Europe/Paris"
    best_day_fraction: float | None = None
    trailing_max_loss: bool = False

    def to_dict(self) -> dict:
        out = asdict(self)
        out["daily_loss_amount"] = self.initial_capital * self.daily_loss_fraction
        out["static_max_loss_floor"] = self.initial_capital * (1 - self.maximum_loss_fraction)
        return out


def ftmo_1step_current_profile() -> FtmoCurrentProfile:
    return FtmoCurrentProfile(
        name=FTMO_1STEP_CURRENT_V1, daily_loss_fraction=0.03,
        minimum_trading_days=0, best_day_fraction=0.50, trailing_max_loss=True,
    )


def ftmo_2step_current_profile(target: float = 0.10) -> FtmoCurrentProfile:
    return FtmoCurrentProfile(
        name=FTMO_2STEP_CURRENT_V1, target=float(target),
        daily_loss_fraction=0.05, minimum_trading_days=4,
    )


def _frame(events) -> pd.DataFrame:
    x = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
    if x.empty:
        return x
    required = {"entry_timestamp", "exit_timestamp", "market", "direction", "net_R", "allocated_risk"}
    missing = required - set(x.columns)
    if missing:
        raise ValueError(f"missing event columns: {sorted(missing)}")
    for c in ("entry_timestamp", "exit_timestamp"):
        x[c] = pd.to_datetime(x[c], utc=True)
    defaults = {"strategy_id": "UNKNOWN", "entry_price": 0.0, "stop_distance": 1.0,
                "commission": 0.0, "swap": 0.0}
    for c, v in defaults.items():
        if c not in x:
            x[c] = v
    return x.sort_values(["entry_timestamp", "strategy_id", "exit_timestamp"]).reset_index(drop=True)


class CurrentFtmoEvaluator:
    """Flat-start bar evaluator for current 1-Step and 2-Step profiles.

    Target completion is causal and requires the account balance to be at or
    above target after all positions have closed.  Floating equity is used for
    breach checks.  The supplied bars are M15 marks; adverse high/low marks are
    intentionally conservative.  No positions are force-closed at the end.
    """
    def __init__(self, profile: FtmoCurrentProfile, initial_capital: float = 1.0):
        self.profile = profile
        self.initial_capital = float(initial_capital)

    def evaluate(self, events, bars_by_market: Mapping[str, pd.DataFrame], start, end) -> dict:
        x = _frame(events)
        start = pd.Timestamp(start).tz_convert("UTC") if pd.Timestamp(start).tzinfo else pd.Timestamp(start, tz="UTC")
        end = pd.Timestamp(end).tz_convert("UTC") if pd.Timestamp(end).tzinfo else pd.Timestamp(end, tz="UTC")
        x = x[(x.entry_timestamp >= start) & (x.entry_timestamp < end)].copy()
        if x.empty:
            return self._result("ALIVE", [], [], None, None, 0.0, 0.0)
        clocks = []
        for market, group in x.groupby("market", sort=True):
            b = bars_by_market.get(market)
            if b is None:
                continue
            b = b.copy(); b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
            b = b[(b.timestamp >= start.floor("15min")) & (b.timestamp <= end)]
            if len(b):
                b["market"] = market
                clocks.append(b[["timestamp", "open", "high", "low", "close", "market"]])
        if not clocks:
            return self._result("ALIVE", [], [], None, None, 0.0, 0.0)
        clock = pd.concat(clocks, ignore_index=True).sort_values(["timestamp", "market"])
        by_market = {m: list(g.itertuples(index=False)) for m, g in x.groupby("market", sort=False)}
        ptr = {m: 0 for m in by_market}; open_pos = []; closed = set(); entered = set()
        balance = self.initial_capital; realized = 0.0; day = None; day_start = balance
        eod_balance = balance; trailing_floor = self.initial_capital * (1 - self.profile.maximum_loss_fraction)
        target_ts = None; target_reached = False; first_breach = None; pass_ts = None
        trading_days = set(); daily_profit = {}; rows = []; max_dd = 0.0; peak = balance
        for bar in clock.itertuples(index=False):
            ts = pd.Timestamp(bar.timestamp); local = _local_day(ts, self.profile.timezone)
            if local != day:
                if day is not None:
                    eod_balance = balance
                    if self.profile.trailing_max_loss:
                        trailing_floor = max(trailing_floor, eod_balance - self.initial_capital * self.profile.maximum_loss_fraction)
                day = local; day_start = balance; daily_profit.setdefault(local, 0.0)
            group = by_market.get(bar.market, [])
            while ptr.get(bar.market, 0) < len(group) and group[ptr[bar.market]].entry_timestamp <= ts:
                p = group[ptr[bar.market]]; ptr[bar.market] += 1; open_pos.append(p)
                entered.add(id(p)); trading_days.add(_local_day(p.entry_timestamp, self.profile.timezone))
            realized_delta = 0.0
            for p in list(open_pos):
                if p.market == bar.market and p.exit_timestamp <= ts:
                    pnl = float(p.net_R) * float(p.allocated_risk) / 0.01 * self.initial_capital
                    costs = float(getattr(p, "commission", 0.0)) + float(getattr(p, "swap", 0.0))
                    pnl += costs / self.initial_capital
                    balance += pnl; realized += pnl; realized_delta += pnl
                    daily_profit[local] += pnl; closed.add(id(p)); open_pos.remove(p)
            floating = 0.0; adverse = 0.0
            for p in open_pos:
                if p.market != bar.market: continue
                sign = 1.0 if str(p.direction).upper() in {"LONG", "BUY"} else -1.0
                denom = max(abs(float(getattr(p, "stop_distance", 1.0))), 1e-12)
                floating += sign * (float(bar.close) - float(p.entry_price)) / denom * float(p.allocated_risk) * self.initial_capital
                bad = float(bar.low) if sign > 0 else float(bar.high)
                adverse += sign * (bad - float(p.entry_price)) / denom * float(p.allocated_risk) * self.initial_capital
            equity = balance + floating; equity_adverse = balance + adverse
            daily_floor = day_start - self.initial_capital * self.profile.daily_loss_fraction
            loss_floor = trailing_floor if self.profile.trailing_max_loss else self.initial_capital * (1 - self.profile.maximum_loss_fraction)
            if equity_adverse < daily_floor - 1e-12:
                first_breach = first_breach or "FAIL_DAILY_LOSS"
            elif equity_adverse < loss_floor - 1e-12:
                first_breach = first_breach or ("FAIL_TRAILING_MAX_LOSS" if self.profile.trailing_max_loss else "FAIL_MAX_LOSS")
            if balance >= self.initial_capital * (1 + self.profile.target) and target_ts is None and not open_pos:
                target_ts = ts; target_reached = True
            best_day = max(daily_profit.values(), default=0.0)
            positive_days = sum(v for v in daily_profit.values() if v > 0)
            ratio = best_day / positive_days if positive_days > 0 else 0.0
            if target_ts is not None and first_breach is None and len(trading_days) >= self.profile.minimum_trading_days:
                if self.profile.best_day_fraction is None or ratio <= self.profile.best_day_fraction + 1e-12:
                    pass_ts = target_ts
            peak = max(peak, equity); max_dd = max(max_dd, peak - equity)
            rows.append({"timestamp": ts, "balance": balance, "floating_pnl": floating,
                         "equity": equity, "equity_adverse": equity_adverse,
                         "daily_floor": daily_floor, "total_loss_floor": loss_floor,
                         "eod_trailing_floor": trailing_floor, "best_day_profit": best_day,
                         "positive_days_profit": positive_days, "best_day_ratio": ratio,
                         "open_positions": len(open_pos), "realized_pnl_delta": realized_delta,
                         "realized_pnl": realized, "target_level": self.initial_capital * (1 + self.profile.target),
                         "daily_breach": equity_adverse < daily_floor,
                         "maximum_loss_breach": equity_adverse < loss_floor})
        pending = target_reached and self.profile.best_day_fraction is not None and pass_ts is None and first_breach is None
        status = "PASS" if pass_ts is not None else (first_breach or ("TARGET_BEST_DAY_PENDING" if pending else "ALIVE"))
        return self._result(status, rows, list(closed), target_ts, pass_ts, max_dd, balance,
                            target_reached=target_reached, trading_days=len(trading_days), first_breach=first_breach)

    def _result(self, status, rows, closed, target_ts, pass_ts, max_dd, balance,
                target_reached=False, trading_days=0, first_breach=None):
        telemetry = pd.DataFrame(rows)
        return {"status": status, "target_reached": bool(target_reached),
                "target_hit_timestamp": target_ts, "pass_timestamp": pass_ts,
                "trading_days": int(trading_days), "positions_closed": len(closed),
                "balance": float(balance), "equity": float(telemetry.equity.iloc[-1]) if len(telemetry) else float(balance),
                "max_drawdown": float(max_dd), "first_breach": first_breach,
                "telemetry": telemetry, "profile": self.profile.name}
