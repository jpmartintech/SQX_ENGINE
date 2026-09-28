"""Deterministic chronological concurrent portfolio replay for Crypto V3."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class PortfolioReplay:
    equity: pd.DataFrame
    trades: pd.DataFrame
    final_equity: float
    total_return: float
    profit_factor: float
    expectancy_r: float
    max_drawdown: float
    peak_concurrent: int
    peak_risk: float
    minimum_equity: float
    economically_valid: bool


def _r_at_price(event, price):
    entry = float(event["entry_price"])
    exit_price = float(event["exit_price"])
    realized = float(event["r"])
    if abs(exit_price - entry) < 1e-15:
        return 0.0
    direction = 1.0 if event["direction"] == "LONG" else -1.0
    progress = direction * (float(price) - entry) / abs(exit_price - entry)
    return realized * progress


def replay_concurrent(events: pd.DataFrame, bars_by_asset: dict[str, pd.DataFrame], *,
                      initial_equity: float = 1.0, total_risk: float = .01,
                      weights: dict[str, float] | None = None) -> PortfolioReplay:
    """Replay overlapping trades with floating equity and fixed fractional risk.

    Events contain evaluator-realized R.  Entry/exit prices are used only for
    chronological mark-to-market; endpoint scaling guarantees evaluator R is
    realized at exit.  Exit events are processed before entries at equal
    timestamps, and all entries at a timestamp use sequential current equity.
    """
    if events is None or len(events) == 0:
        empty = pd.DataFrame(columns=["timestamp", "equity", "cash", "floating", "drawdown", "open_positions", "risk"])
        return PortfolioReplay(empty, pd.DataFrame(), initial_equity, 0.0, 0.0, 0.0, 0.0, 0, 0.0, initial_equity, True)
    e = events.copy()
    for c in ("entry_time", "exit_time"): e[c] = pd.to_datetime(e[c], utc=True)
    # ``strategy_key`` is optional for backward compatibility, but is required
    # by multi-asset product runs when the same definition hash exists on more
    # than one market.
    if "strategy_key" not in e.columns:
        e["strategy_key"] = e["hash"].astype(str)
    e = e.sort_values(["entry_time", "exit_time", "strategy_key"], kind="mergesort").reset_index(drop=True)
    entries_by_time = {t: g.to_dict("records") for t, g in e.groupby("entry_time", sort=False)}
    weights = weights or {h: 1.0 for h in e.strategy_key.unique()}
    weight_sum = float(sum(weights.values())) or 1.0
    weights = {k: float(v) / weight_sum for k, v in weights.items()}
    times = set(e.entry_time.tolist()) | set(e.exit_time.tolist())
    for asset, bars in bars_by_asset.items():
        b = bars.copy(); b.timestamp = pd.to_datetime(b.timestamp, utc=True)
        times.update(b.timestamp.tolist())
    times = sorted(times)
    cash = float(initial_equity); positions = []; curve=[]; closed=[]; peak=initial_equity
    peak_concurrent=0; peak_risk=0.0
    lookup = {}
    for asset,bars in bars_by_asset.items():
        b=bars.sort_values("timestamp"); lookup[asset]=(pd.to_datetime(b.timestamp,utc=True).astype("int64").to_numpy(),b.close.to_numpy(float))
    def price_at(asset, t):
        ts,px=lookup[asset]; i=int(np.searchsorted(ts,pd.Timestamp(t).value,side="right")-1)
        return float(px[max(0,min(i,len(px)-1))])
    for t in times:
        # Realize exits first.
        for pos in list(positions):
            if pos["event"]["exit_time"] == t:
                cash += pos["risk_budget"] * float(pos["event"]["r"])
                closed.append({**pos["event"],"risk_budget":pos["risk_budget"],"realized_pnl":pos["risk_budget"]*float(pos["event"]["r"]),"entry_equity":pos["entry_equity"]})
                positions.remove(pos)
        # New entries use equity known at this timestamp.
        floating = sum(p["risk_budget"] * _r_at_price(p["event"], price_at(p["event"]["asset"], t)) for p in positions)
        equity = cash + floating
        for ev in entries_by_time.get(t, []):
            budget = max(0.0, equity) * total_risk * weights.get(ev.get("strategy_key", ev["hash"]), 0.0)
            positions.append({"event":ev,"risk_budget":budget,"entry_equity":equity})
        # A frozen strategy can legitimately enter and exit on the same
        # timestamp when the next-bar trade is resolved inside that bar.  The
        # event is realized immediately; otherwise it would remain open until
        # the final force-close and distort concurrency, PF, and expectancy.
        for pos in list(positions):
            if pos["event"]["exit_time"] == t:
                pnl = pos["risk_budget"] * float(pos["event"]["r"])
                cash += pnl
                closed.append({**pos["event"],"risk_budget":pos["risk_budget"],"realized_pnl":pnl,"entry_equity":pos["entry_equity"]})
                positions.remove(pos)
        floating = sum(p["risk_budget"] * _r_at_price(p["event"], price_at(p["event"]["asset"], t)) for p in positions)
        equity = cash + floating; peak=max(peak,equity)
        peak_concurrent=max(peak_concurrent,len(positions)); peak_risk=max(peak_risk,sum(p["risk_budget"] for p in positions))
        curve.append({"timestamp":t,"equity":equity,"cash":cash,"floating":floating,"drawdown":(equity-peak)/peak if peak else -1.0,"open_positions":len(positions),"risk":sum(p["risk_budget"] for p in positions)})
    # Any open position at the end is force-closed at the final mark.
    if positions:
        t=times[-1]
        for p in positions:
            r=_r_at_price(p["event"],price_at(p["event"]["asset"],t)); cash += p["risk_budget"]*r
            closed.append({**p["event"],"risk_budget":p["risk_budget"],"realized_pnl":p["risk_budget"]*r,"entry_equity":p["entry_equity"],"forced_close":True})
    curve_df=pd.DataFrame(curve); trade_df=pd.DataFrame(closed)
    final=float(cash); pn=trade_df.realized_pnl.to_numpy(float) if len(trade_df) else np.array([])
    wins=pn[pn>0]; losses=pn[pn<0]; pf=float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum() else (float("inf") if len(wins) else 0.0)
    rs=trade_df.r.to_numpy(float) if len(trade_df) else np.array([])
    minimum=float(curve_df.equity.min()) if len(curve_df) else final
    return PortfolioReplay(curve_df,trade_df,final,final/initial_equity-1,pf,float(rs.mean()) if len(rs) else 0.0,float(curve_df.drawdown.min()) if len(curve_df) else 0.0,peak_concurrent,peak_risk,minimum,minimum >= 0.0)
