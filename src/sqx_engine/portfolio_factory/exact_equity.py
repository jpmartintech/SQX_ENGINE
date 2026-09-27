"""Bar-resolution, normalized equity replay for FTMO evaluation research.

This layer deliberately accepts explicit position geometry.  It never invents
stops, spreads, swaps, or tick paths when those inputs are absent.  The replay
is therefore exact with respect to supplied bar/cost/position data and is
explicitly partial when those data are incomplete.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
import json
import numpy as np
import pandas as pd

from .ftmo_v2 import Ftmo2StepProfile, _local_day


@dataclass(frozen=True)
class CostStatus:
    spread: str = "COST_UNRESOLVED"
    commission: str = "COST_UNRESOLVED"
    swap: str = "COST_UNRESOLVED"


@dataclass
class ReplayPosition:
    strategy_id: str
    market: str
    timeframe: str
    direction: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    stop_price: float | None
    target_price: float | None
    allocated_risk_fraction: float | None
    volume: float | None = None
    contract_value: float | None = None
    commission_entry: float = 0.0
    commission_exit: float = 0.0
    swap: float = 0.0
    net_return: float | None = None

    @property
    def sign(self) -> float:
        return 1.0 if self.direction.upper() in {"BUY", "LONG"} else -1.0

    @property
    def initial_stop_distance(self) -> float | None:
        if self.stop_price is None:
            return None
        return abs(self.entry_price - self.stop_price)


def load_ohlc(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing OHLC columns: {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if not frame.timestamp.is_monotonic_increasing:
        raise ValueError("OHLC timestamps are not monotonic")
    if (frame[["high", "low"]].isna().any().any() or (frame.high < frame.low).any()):
        raise ValueError("invalid OHLC values")
    return frame


def _as_events(events: pd.DataFrame | Iterable[dict]) -> pd.DataFrame:
    frame = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
    required = {"entry_time", "exit_time", "direction", "entry_price"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing position columns: {sorted(missing)}")
    for c in ("entry_time", "exit_time"):
        frame[c] = pd.to_datetime(frame[c], utc=True)
    defaults = {
        "strategy_id": "UNKNOWN",
        "market": "UNKNOWN",
        "timeframe": "UNKNOWN",
        "stop_price": np.nan,
        "target_price": np.nan,
        "allocated_risk_fraction": np.nan,
        "volume": np.nan,
        "contract_value": np.nan,
        "commission_entry": 0.0,
        "commission_exit": 0.0,
        "swap": 0.0,
        "net_return": np.nan,
    }
    for c, value in defaults.items():
        if c not in frame:
            frame[c] = value
    return frame.sort_values(["entry_time", "strategy_id", "exit_time"]).reset_index(drop=True)


def _position(row) -> ReplayPosition:
    return ReplayPosition(
        strategy_id=str(row.strategy_id), market=str(row.market), timeframe=str(row.timeframe),
        direction=str(row.direction), entry_time=row.entry_time, exit_time=row.exit_time,
        entry_price=float(row.entry_price), stop_price=None if pd.isna(row.stop_price) else float(row.stop_price),
        target_price=None if pd.isna(row.target_price) else float(row.target_price),
        allocated_risk_fraction=None if pd.isna(row.allocated_risk_fraction) else float(row.allocated_risk_fraction),
        volume=None if pd.isna(row.volume) else float(row.volume),
        contract_value=None if pd.isna(row.contract_value) else float(row.contract_value),
        commission_entry=float(row.commission_entry), commission_exit=float(row.commission_exit),
        swap=float(row.swap), net_return=None if pd.isna(row.net_return) else float(row.net_return),
    )


def _path_prices(bar, order: str):
    return [bar.open, bar.high, bar.low, bar.close] if order == "O-H-L-C" else [bar.open, bar.low, bar.high, bar.close]


class BarEquityReplay:
    """Replay explicit positions on bars with conservative equity probes."""

    def __init__(self, profile: Ftmo2StepProfile | None = None, initial_equity: float = 1.0,
                 path_policy: str = "BAR_PATH_CONSERVATIVE"):
        if path_policy not in {"BAR_PATH_CONSERVATIVE", "BAR_PATH_OHLC_SCENARIOS"}:
            raise ValueError("unsupported path policy")
        self.profile = profile or Ftmo2StepProfile()
        self.initial_equity = float(initial_equity)
        self.path_policy = path_policy

    def replay(self, events: pd.DataFrame | Iterable[dict], bars: pd.DataFrame,
               market: str | None = None) -> dict:
        frame = _as_events(events)
        bars = bars.copy()
        bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
        if frame.empty:
            return {"status": "RIGHT_CENSORED", "telemetry": pd.DataFrame(), "positions": 0,
                    "intrabar_ambiguous": 0, "equity_mtm_exact": False}
        positions = [_position(row) for row in frame.itertuples(index=False)]
        if market:
            positions = [p for p in positions if p.market == market]
        if not positions:
            return {"status": "RIGHT_CENSORED", "telemetry": pd.DataFrame(), "positions": 0,
                    "intrabar_ambiguous": 0, "equity_mtm_exact": False}
        first, last = min(p.entry_time for p in positions), max(p.exit_time for p in positions)
        clock = bars[(bars.timestamp >= first.floor("15min")) & (bars.timestamp <= last)].copy()
        balance = self.initial_equity
        peak = balance
        realized = 0.0
        open_positions: list[ReplayPosition] = []
        entered = set()
        closed = set()
        daily_start = {}
        day = None
        rows = []
        ambiguous = 0
        breach = None
        for bar in clock.itertuples(index=False):
            ts = bar.timestamp
            local_day = _local_day(ts, self.profile.timezone)
            if local_day != day:
                day = local_day
                daily_start[day] = balance
            for i, p in enumerate(positions):
                if i not in entered and p.entry_time <= ts:
                    entered.add(i); open_positions.append(p)
                    balance += p.commission_entry / self.initial_equity
            for i, p in enumerate(positions):
                if i not in closed and p.exit_time <= ts and i in entered:
                    pnl = self._realized(p)
                    balance += pnl + (p.commission_exit + p.swap) / self.initial_equity
                    realized += pnl + (p.commission_exit + p.swap) / self.initial_equity
                    closed.add(i)
                    open_positions = [x for x in open_positions if x is not p]
            floating_close = sum(self._floating(p, bar.close) for p in open_positions)
            floating_adverse = sum(self._floating(p, bar.low if p.sign > 0 else bar.high) for p in open_positions)
            equity_close = balance + floating_close
            equity_adverse = balance + floating_adverse
            scenario_equities = [self._scenario_equity(balance, open_positions, bar, "O-H-L-C"),
                                 self._scenario_equity(balance, open_positions, bar, "O-L-H-C")]
            equity_open = balance + sum(self._floating(p, bar.open) for p in open_positions)
            equity = min(equity_adverse, *scenario_equities) if self.path_policy == "BAR_PATH_CONSERVATIVE" else min(scenario_equities)
            possible_both = sum(self._both_hit(p, bar) for p in open_positions)
            ambiguous += possible_both
            floor = daily_start[day] - self.profile.daily_loss_fraction * self.initial_equity
            if equity < self.profile.maximum_loss_limit:
                breach = breach or "FAIL_MAX_LOSS"
            elif equity < floor:
                breach = breach or "FAIL_DAILY"
            peak = max(peak, equity)
            rows.append({"timestamp": ts, "balance": balance, "floating_pnl": equity_close - balance,
                         "equity": equity, "equity_open": equity_open, "equity_adverse": equity_adverse,
                         "equity_close": equity_close, "open_positions": len(open_positions),
                         "aggregate_initial_open_risk": sum(self._open_risk(p) for p in open_positions),
                         "realized_pnl": realized, "date_ftmo": day, "daily_loss_floor": floor,
                         "daily_breach": equity < floor, "maximum_loss_breach": equity < self.profile.maximum_loss_limit})
        telemetry = pd.DataFrame(rows)
        final = "FAIL_MAX_LOSS" if breach == "FAIL_MAX_LOSS" else "FAIL_DAILY" if breach else "RIGHT_CENSORED"
        return {"status": final, "telemetry": telemetry, "positions": len(positions),
                "positions_closed": len(closed), "intrabar_ambiguous": int(ambiguous),
                "max_equity_drawdown": float(((telemetry.equity.cummax() - telemetry.equity).max()) if len(telemetry) else 0),
                "equity_mtm_exact": False, "path_policy": self.path_policy,
                "cost_status": asdict(CostStatus(commission="COST_EXACT" if frame[["commission_entry", "commission_exit"]].to_numpy().any() else "COST_UNRESOLVED",
                                                  swap="COST_EXACT" if frame.swap.to_numpy().any() else "COST_UNRESOLVED"))}

    def _contract_value(self, p):
        return p.contract_value if p.contract_value is not None else 1.0

    def _realized(self, p):
        if p.net_return is not None:
            return p.net_return
        return p.sign * (0.0) if p.initial_stop_distance is None else 0.0

    def _floating(self, p, mark):
        return p.sign * (float(mark) - p.entry_price) * self._contract_value(p) / self.initial_equity

    def _open_risk(self, p):
        if p.allocated_risk_fraction is not None:
            return p.allocated_risk_fraction
        if p.stop_price is not None:
            return abs(p.stop_price - p.entry_price) * self._contract_value(p) / self.initial_equity
        return 0.0

    def _both_hit(self, p, bar):
        if p.stop_price is None or p.target_price is None:
            return False
        return bool(bar.low <= p.stop_price <= bar.high and bar.low <= p.target_price <= bar.high)

    def _scenario_equity(self, balance, positions, bar, order):
        worst = balance
        for p in positions:
            mark = min(_path_prices(bar, order)) if p.sign > 0 else max(_path_prices(bar, order))
            worst += self._floating(p, mark)
        return worst


class FtmoEpisodeEvaluator:
    """Normalized, flat-start FTMO episode evaluator.

    Events carry ``net_R`` and ``allocated_risk``.  One R is therefore
    ``allocated_risk / 0.01`` normalized account units; ``initial_capital``
    only changes the reporting currency.  The evaluator keeps balance and
    floating equity separate, marks open positions on M15 bars, uses
    Europe/Paris daily floors, and never force-closes positions at the
    episode boundary.  It is intentionally conservative at bar resolution.
    """
    def __init__(self, profile: Ftmo2StepProfile | None = None, initial_capital: float = 1.0):
        self.profile = profile or Ftmo2StepProfile()
        self.initial_capital = float(initial_capital)

    @staticmethod
    def _normal_events(events, start, end):
        frame = events.copy() if isinstance(events, pd.DataFrame) else pd.DataFrame(events)
        if frame.empty:
            return frame
        for c in ("entry_timestamp", "exit_timestamp"):
            frame[c] = pd.to_datetime(frame[c], utc=True)
        frame = frame[(frame.entry_timestamp >= start) & (frame.entry_timestamp < end)].copy()
        for c, value in (("allocated_risk", 0.0), ("net_R", 0.0), ("market", "UNKNOWN"), ("direction", "LONG")):
            if c not in frame:
                frame[c] = value
        frame["allocated_risk"] = frame.allocated_risk.astype(float)
        frame["net_R"] = frame.net_R.astype(float)
        frame["_row"] = np.arange(len(frame))
        return frame.sort_values(["entry_timestamp", "strategy_id", "exit_timestamp"] if "strategy_id" in frame else ["entry_timestamp", "exit_timestamp"]).reset_index(drop=True)

    def evaluate(self, events, bars_by_market, start, end, target=0.10):
        start = pd.Timestamp(start); end = pd.Timestamp(end)
        if start.tzinfo is None: start = start.tz_localize("UTC")
        else: start = start.tz_convert("UTC")
        if end.tzinfo is None: end = end.tz_localize("UTC")
        else: end = end.tz_convert("UTC")
        frame = self._normal_events(events, start, end)
        if frame.empty:
            return {"status":"ALIVE", "target_hit":False, "target_hit_timestamp":None, "telemetry":pd.DataFrame(), "positions_open_end":0, "trading_days":0}
        clocks=[]
        for market, group in frame.groupby("market", sort=True):
            bars = bars_by_market.get(market)
            if bars is None: continue
            b = bars.copy(); b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
            b = b[(b.timestamp >= start) & (b.timestamp <= end)].copy()
            if len(b):
                b["market"] = market; clocks.append(b[["timestamp","open","high","low","close","market"]])
        if not clocks:
            return {"status":"ALIVE", "target_hit":False, "target_hit_timestamp":None, "telemetry":pd.DataFrame(), "positions_open_end":len(frame), "trading_days":0}
        clock = pd.concat(clocks, ignore_index=True).sort_values(["timestamp","market"]).reset_index(drop=True)
        by_market = {m:list(x.itertuples(index=False)) for m,x in frame.groupby("market", sort=False)}
        entry_ptr = {m:0 for m in by_market}; entered=[]; closed=set(); open_positions=[]
        balance=self.initial_capital; realized=0.0; daily_start={}; current_day=None; target_hit=False; target_ts=None; pass_ts=None; first_breach=None; peak=self.initial_capital; rows=[]
        for bar in clock.itertuples(index=False):
            ts=pd.Timestamp(bar.timestamp); day=_local_day(ts, self.profile.timezone)
            if day != current_day:
                current_day=day; daily_start[day]=balance
            market_positions=by_market.get(bar.market, [])
            while entry_ptr.get(bar.market,0) < len(market_positions) and market_positions[entry_ptr[bar.market]].entry_timestamp <= ts:
                p=market_positions[entry_ptr[bar.market]]; entered.append(p); open_positions.append(p); entry_ptr[bar.market]+=1
            realized_delta=0.0
            for p in list(open_positions):
                if p.market == bar.market and p.exit_timestamp <= ts:
                    pnl=float(p.net_R*p.allocated_risk)*self.initial_capital
                    balance += pnl; realized += pnl; realized_delta += pnl; closed.add(id(p)); open_positions.remove(p)
            floating=0.0; adverse=0.0; favorable=0.0
            for p in open_positions:
                if p.market != bar.market: continue
                sign=1.0 if str(p.direction).upper() in {"LONG","BUY"} else -1.0
                denom=max(abs(float(p.entry_price)-float(p.stop_price)), 1e-12) if hasattr(p,"stop_price") and pd.notna(p.stop_price) else 1.0
                mark=float(bar.close); bad=float(bar.low) if sign>0 else float(bar.high); good=float(bar.high) if sign>0 else float(bar.low)
                floating += sign*(mark-float(p.entry_price))/denom*float(p.allocated_risk)*self.initial_capital
                adverse += sign*(bad-float(p.entry_price))/denom*float(p.allocated_risk)*self.initial_capital
                favorable += sign*(good-float(p.entry_price))/denom*float(p.allocated_risk)*self.initial_capital
            equity=balance+floating; equity_adverse=balance+adverse; equity_favorable=balance+favorable
            floor=daily_start[day]-self.profile.daily_loss_fraction*self.initial_capital
            total_floor=self.profile.maximum_loss_limit*self.initial_capital
            if equity_adverse < total_floor: first_breach=first_breach or "MAX_LOSS"
            elif equity_adverse < floor: first_breach=first_breach or "DAILY_LOSS"
            target_level=self.initial_capital*(1+target)
            if (equity >= target_level-1e-10*max(1.0,self.initial_capital) or equity_favorable >= target_level-1e-10*max(1.0,self.initial_capital)) and target_ts is None:
                target_hit=True; target_ts=ts
            # Positions already active at the target must be closed; future
            # signals in the episode do not invalidate a causal pass.
            if target_hit and not open_positions and first_breach is None:
                pass_ts=target_ts
            peak=max(peak,equity); rows.append({"timestamp":ts,"balance":balance,"floating_pnl":floating,"equity":equity,"equity_adverse":equity_adverse,"equity_favorable":equity_favorable,"realized_pnl":realized,"realized_pnl_delta":realized_delta,"open_positions":len(open_positions),"open_initial_risk":float(sum(p.allocated_risk for p in open_positions)*self.initial_capital),"daily_floor":floor,"total_loss_floor":total_floor,"target_level":self.initial_capital*(1+target),"date_ftmo":day,"daily_breach":equity_adverse<floor,"maximum_loss_breach":equity_adverse<total_floor})
        telemetry=pd.DataFrame(rows)
        all_closed=len(closed)==len(frame)
        status="PASS" if pass_ts is not None else "FAIL" if first_breach else "ALIVE"
        return {"status":status,"target_hit":target_hit,"target_hit_timestamp":target_ts,"target_hit_equity":float(telemetry.loc[telemetry.timestamp==target_ts,"equity"].iloc[0]) if target_ts is not None and len(telemetry.loc[telemetry.timestamp==target_ts]) else None,"telemetry":telemetry,"positions_open_end":len(open_positions),"trading_days":len({p.entry_timestamp.tz_convert(self.profile.timezone).date() for p in entered}),"balance":balance,"equity":float(telemetry.equity.iloc[-1]) if len(telemetry) else balance,"max_drawdown":float((telemetry.equity.cummax()-telemetry.equity).max()) if len(telemetry) else 0.0,"first_breach":first_breach,"intrabar_target_observation":target_ts is not None}


def inventory_dataset(path: str | Path, market: str, timeframe: str, kind: str = "native") -> dict:
    frame = load_ohlc(path)
    return {"market": market, "timeframe": timeframe, "path": str(path), "kind": kind,
            "rows": int(len(frame)), "start": str(frame.timestamp.min()), "end": str(frame.timestamp.max()),
            "columns": list(frame.columns), "duplicates": int(frame.timestamp.duplicated().sum()),
            "monotonic": bool(frame.timestamp.is_monotonic_increasing)}
