"""Bounded exact replay diagnostic for diversification of failed Prop V1 raw material."""
from __future__ import annotations

import hashlib, importlib.util, json, resource, time
from pathlib import Path
import numpy as np
import pandas as pd

from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.data.loader import load_ohlcv
from sqx_engine.features import prepare_features
from sqx_engine.portfolio_factory.exact_equity import FtmoEpisodeEvaluator
from sqx_engine.strategy import StrategyDefinition

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/prop_factory_autonomous_supervisor"
DATA = {
    ("EURUSD", "M15"): ROOT / "data/cloud/EURUSD_M15.csv",
    ("EURUSD", "H1"): ROOT / "data/derived/EURUSD_H1_11d571e8bb3d_143197.csv",
    ("XAUUSD", "M15"): ROOT / "data/cloud/XAUUSD_M15.csv",
    ("XAUUSD", "H1"): ROOT / "data/derived/XAUUSD_H1_ace62dd3d22f_136885.csv",
}


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def ledger(strategy, market, timeframe, frame):
    a, b = int(len(frame) * .60), int(len(frame) * .80)
    data = frame.iloc[:b].reset_index(drop=True)
    features = prepare_features(data, grammar_version="v1.7")
    ev = FastEvaluator(data, features, initial_capital=10000, spread=0.0, slippage=0.0, cache_size=0, engine="auto")
    result = ev.evaluate(strategy, rich=True)
    times = {pd.Timestamp(t).tz_convert("UTC"): i for i, t in enumerate(data.timestamp)}
    atr = np.asarray(features["atr_14"], dtype=float)
    rows = []
    for t in result.trades:
        entry = pd.Timestamp(t["entry_time"], tz="UTC") if pd.Timestamp(t["entry_time"]).tzinfo is None else pd.Timestamp(t["entry_time"]).tz_convert("UTC")
        exit_time = pd.Timestamp(t["exit_time"], tz="UTC") if pd.Timestamp(t["exit_time"]).tzinfo is None else pd.Timestamp(t["exit_time"]).tz_convert("UTC")
        ei = times[entry]; risk = float(atr[ei - 1] * strategy.stop_atr); ep = float(data.open.iloc[ei]); sign = 1 if t["direction"] == "LONG" else -1
        stop = ep - risk if sign > 0 else ep + risk; target = ep + risk * strategy.target_atr / strategy.stop_atr if sign > 0 else ep - risk * strategy.target_atr / strategy.stop_atr
        xp = stop if t["reason"] == "STOP" else target if t["reason"] == "TARGET" else float(data.close.iloc[times[exit_time]])
        rows.append({"strategy_id": strategy.readable_id, "market": market, "timeframe": timeframe, "direction": t["direction"], "entry_timestamp": entry, "exit_timestamp": exit_time, "entry_price": ep, "stop_price": stop, "target_price": target, "exit_price": xp, "net_R": t["r"]})
    x = pd.DataFrame(rows)
    if len(x): x["split"] = np.where(x.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize() < x.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize().sort_values().iloc[max(1, int(x.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize().nunique() * .60))], "DEVELOPMENT", "VALIDATION")
    return x


def accepted(members, by, start, end, risk, cap):
    frames = []
    weight = 1.0 / len(members)
    for sid in members:
        x = by[sid]; x = x[(x.entry_timestamp >= start) & (x.entry_timestamp < end)].copy()
        if len(x): x["allocated_risk"] = risk * weight; frames.append(x)
    if not frames: return pd.DataFrame()
    x = pd.concat(frames, ignore_index=True).sort_values(["entry_timestamp", "strategy_id", "exit_timestamp"])
    active = []; out = []
    for row in x.itertuples(index=False):
        active = [a for a in active if a.exit_timestamp > row.entry_timestamp]
        if sum(a.allocated_risk for a in active) + row.allocated_risk <= cap + 1e-12:
            out.append(row); active.append(row)
    return pd.DataFrame(out)


def main():
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    defs = []
    for p in (ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_02/forensics_eur/prop_candidates_replay.parquet", ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_02/forensics_xau/prop_candidates_replay.parquet"):
        defs.append(pd.read_parquet(p))
    defs = pd.concat(defs, ignore_index=True).drop_duplicates("strategy_id")
    selected = []
    for cell, group in defs.groupby(["market", "timeframe"], sort=True):
        selected.extend(group.sort_values("strategy_id").strategy_id.head(5).tolist())
    selected_defs = defs[defs.strategy_id.isin(selected)].copy()
    by = {}
    bars = {}
    for (market, timeframe), group in selected_defs.groupby(["market", "timeframe"], sort=True):
        frame = load_ohlcv(DATA[(market, timeframe)])
        bars.setdefault(market, load_ohlcv(DATA[(market, "M15")]))
        for row in group.itertuples(index=False):
            s = StrategyDefinition.from_json(row.strategy_json)
            x = ledger(s, market, timeframe, frame)
            if len(x): by[row.strategy_id] = x
    ids = sorted(by)
    days = sorted(pd.concat(list(by.values())).entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize().unique())
    episodes = []
    for i in range(len(days) - 4): episodes.append((days[i], days[i + 4] + pd.Timedelta(days=1), "DEVELOPMENT" if i < int(len(days) * .6) else "VALIDATION"))
    families = {
        "SAME_EUR_M15": [x for x in ids if x in selected_defs[(selected_defs.market == "EURUSD") & (selected_defs.timeframe == "M15")].strategy_id.tolist()],
        "SAME_XAU_M15": [x for x in ids if x in selected_defs[(selected_defs.market == "XAUUSD") & (selected_defs.timeframe == "M15")].strategy_id.tolist()],
        "CROSS_MARKET_M15": [x for x in ids if x in selected_defs[(selected_defs.timeframe == "M15")].strategy_id.tolist()],
        "CROSS_MARKET_TIMEFRAME": ids,
    }
    rows = []
    for family, members in families.items():
        for risk, cap in ((.01, .02), (.02, .03)):
            for start, end, split in episodes[::max(1, len(episodes) // 30)]:
                ev = accepted(members, by, start, end, risk, cap)
                for target, phase in ((.10, "CHALLENGE"), (.05, "VERIFICATION")):
                    result = FtmoEpisodeEvaluator().evaluate(ev, bars, start, end, target=target)
                    t = result.get("telemetry", pd.DataFrame())
                    rows.append({"family": family, "members": len(members), "risk": risk, "cap": cap, "start": start, "split": split, "phase": phase, "status": result.get("status"), "max_intraperiod": float(t.equity.max() - 1.0) if len(t) else 0.0, "p01": float(t.equity.min() - 1.0) if len(t) else 0.0, "open_risk_peak": float(t.open_initial_risk.max()) if len(t) else 0.0, "daily_breach": result.get("status") == "FAIL_DAILY", "max_loss_breach": result.get("status") == "FAIL_MAX_LOSS", "admitted": len(ev)})
    result = pd.DataFrame(rows); result.to_parquet(OUT / "diversification_exact_results.parquet", index=False)
    summary = []
    for (family, risk, cap, phase, split), g in result.groupby(["family", "risk", "cap", "phase", "split"], sort=True):
        summary.append({"family": family, "risk": risk, "cap": cap, "phase": phase, "split": split, "episodes": len(g), "pass": float((g.status == "PASS").mean()), "fail": float(g.status.str.startswith("FAIL").mean()), "alive": float((g.status == "ALIVE").mean()), "p95_max_intraperiod": float(g.max_intraperiod.quantile(.95)), "p99_max_intraperiod": float(g.max_intraperiod.quantile(.99)), "max_max_intraperiod": float(g.max_intraperiod.max()), "p05_equity": float(g.p01.quantile(.05)), "peak_open_risk": float(g.open_risk_peak.max())})
    dump("diversification_summary.json", {"authority": "FtmoEpisodeEvaluator", "sample_strategies": len(ids), "families": summary, "oos_accesses": 0, "interpretation": "Diagnostic only; no candidate promotion or policy change."})
    dump("diversification_performance.json", {"runtime_seconds": time.perf_counter() - started, "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "oos_accesses": 0, "strategies": len(ids), "episodes": len(episodes)})
    print(json.dumps({"strategies": len(ids), "episodes": len(episodes), "rows": len(result), "runtime_seconds": time.perf_counter() - started, "oos_accesses": 0}, indent=2))


if __name__ == "__main__": main()
