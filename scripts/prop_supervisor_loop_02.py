"""Supervisor diagnostics for Prop V1 loss-cluster predictability.

This is deliberately diagnostic.  It never promotes strategies, changes
the Prop policy, or reads OOS data.  State bins are learned on DEVELOPMENT
and applied unchanged to VALIDATION.
"""
from __future__ import annotations

import hashlib
import json
import resource
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/prop_factory_autonomous_supervisor"
FORENSICS = ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_02"
DATA = {
    "EURUSD": ROOT / "data/cloud/EURUSD_M15.csv",
    "XAUUSD": ROOT / "data/cloud/XAUUSD_M15.csv",
}


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def _features(market):
    x = pd.read_csv(DATA[market], usecols=["timestamp", "open", "high", "low", "close"])
    x["timestamp"] = pd.to_datetime(x.timestamp, utc=True)
    x = x.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    close = x.close.astype(float)
    tr = pd.concat([x.high - x.low, (x.high - close.shift()).abs(), (x.low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    x["ret_1"] = close.pct_change(1)
    x["ret_4"] = close.pct_change(4)
    x["ret_16"] = close.pct_change(16)
    x["vol_16"] = x.ret_1.rolling(16, min_periods=16).std()
    x["atr_pct"] = atr / close.replace(0, np.nan)
    x["range_pct"] = (x.high - x.low) / close.replace(0, np.nan)
    x["trend_sign"] = np.sign(close - close.shift(16))
    x["vol_change"] = x.atr_pct / x.atr_pct.rolling(64, min_periods=32).median()
    return x[["timestamp", "ret_1", "ret_4", "ret_16", "vol_16", "atr_pct", "range_pct", "trend_sign", "vol_change"]]


def _trade_targets(g):
    g = g.sort_values(["strategy_id", "entry_timestamp"]).copy()
    g["loss"] = (g.net_R.astype(float) < 0).astype(float)
    g["stop"] = g.exit_reason.astype(str).str.upper().eq("STOP").astype(float)
    g["prior_loss_streak"] = 0.0
    g["prior_loss_1d"] = 0.0
    g["prior_loss_3d"] = 0.0
    g["prior_signal_1d"] = 0.0
    g["prior_signal_3d"] = 0.0
    g["next3_loss_rate"] = np.nan
    g["next5_loss_rate"] = np.nan
    g["next5_R"] = np.nan
    for sid, ix in g.groupby("strategy_id", sort=False).groups.items():
        idx = np.asarray(ix)
        z = g.loc[idx].sort_values("entry_timestamp")
        times = z.entry_timestamp
        loss = z.loss.to_numpy(float)
        r = z.net_R.to_numpy(float)
        streak = np.zeros(len(z)); cur = 0
        for i in range(len(z)):
            streak[i] = cur
            cur = cur + 1 if loss[i] else 0
        # Searchsorted keeps the causal lookback O(n log n) per strategy;
        # the previous prototype used an O(n^2) boolean mask loop.
        t_ns = times.astype("int64").to_numpy()
        one = 86_400_000_000_000; three = 3 * one
        c_loss = np.r_[0.0, np.cumsum(loss)]
        c_one = np.searchsorted(t_ns, t_ns - one, side="left")
        c_three = np.searchsorted(t_ns, t_ns - three, side="left")
        positions = np.arange(len(z))
        prior_1d = c_loss[positions] - c_loss[c_one]
        prior_3d = c_loss[positions] - c_loss[c_three]
        sig_1d = positions - c_one
        sig_3d = positions - c_three
        c_loss_f = np.r_[0.0, np.cumsum(loss)]
        c_r_f = np.r_[0.0, np.cumsum(r)]
        end3 = np.minimum(positions + 4, len(z)); end5 = np.minimum(positions + 6, len(z))
        count3 = end3 - (positions + 1); count5 = end5 - (positions + 1)
        fut3 = (c_loss_f[end3] - c_loss_f[positions + 1]) / np.maximum(count3, 1)
        fut5 = (c_loss_f[end5] - c_loss_f[positions + 1]) / np.maximum(count5, 1)
        futr = c_r_f[end5] - c_r_f[positions + 1]
        fut3[count3 <= 0] = np.nan; fut5[count5 <= 0] = np.nan; futr[count5 <= 0] = np.nan
        g.loc[z.index, "prior_loss_streak"] = streak
        g.loc[z.index, "prior_loss_1d"] = prior_1d
        g.loc[z.index, "prior_loss_3d"] = prior_3d
        g.loc[z.index, "prior_signal_1d"] = sig_1d
        g.loc[z.index, "prior_signal_3d"] = sig_3d
        g.loc[z.index, "next3_loss_rate"] = fut3
        g.loc[z.index, "next5_loss_rate"] = fut5
        g.loc[z.index, "next5_R"] = futr
    return g


def _attach_state(g, market):
    f = _features(market)
    g = g.sort_values("entry_timestamp")
    return pd.merge_asof(g, f, left_on="entry_timestamp", right_on="timestamp", direction="backward").drop(columns=["timestamp"])


def _state_report(g):
    state_cols = ["ret_1", "ret_4", "ret_16", "vol_16", "atr_pct", "range_pct", "trend_sign", "vol_change", "prior_loss_streak", "prior_loss_1d", "prior_loss_3d", "prior_signal_1d", "prior_signal_3d"]
    rows = []
    for col in state_cols:
        train = g[g.split.astype(str).str.upper().eq("DEVELOPMENT") & g[col].notna() & g.next5_loss_rate.notna()][[col, "next5_loss_rate", "next3_loss_rate", "next5_R"]].copy()
        val = g[g.split.astype(str).str.upper().eq("VALIDATION") & g[col].notna() & g.next5_loss_rate.notna()][[col, "next5_loss_rate", "next3_loss_rate", "next5_R"]].copy()
        if len(train) < 100:
            continue
        q = np.unique(train[col].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy())
        if len(q) < 2:
            continue
        train["bin"] = pd.cut(train[col], bins=[-np.inf, *q, np.inf], labels=False, duplicates="drop")
        val["bin"] = pd.cut(val[col], bins=[-np.inf, *q, np.inf], labels=False, duplicates="drop")
        overall = float(train.next5_loss_rate.mean())
        groups = train.groupby("bin", observed=True).agg(n=("next5_loss_rate", "size"), loss_rate=("next5_loss_rate", "mean"), next3_loss_rate=("next3_loss_rate", "mean"), next5_R=("next5_R", "mean")).reset_index()
        vg = val.groupby("bin", observed=True).agg(n=("next5_loss_rate", "size"), loss_rate=("next5_loss_rate", "mean"), next3_loss_rate=("next3_loss_rate", "mean"), next5_R=("next5_R", "mean")).reset_index()
        merged = groups.merge(vg, on="bin", how="outer", suffixes=("_dev", "_val"))
        worst = groups.loc[groups.loss_rate.idxmax()]
        worst_val = vg.loc[vg.loss_rate.idxmax()] if len(vg) else None
        rows.append({"state": col, "development_n": int(len(train)), "validation_n": int(len(val)), "development_overall_loss_rate": overall, "development_worst_bin_loss_rate": float(worst.loss_rate), "development_worst_bin_n": int(worst.n), "validation_worst_bin_loss_rate": float(worst_val.loss_rate) if worst_val is not None else None, "validation_worst_bin_n": int(worst_val.n) if worst_val is not None else 0, "dev_val_direction_consistent": bool(worst.loss_rate > overall and worst_val is not None and worst_val.loss_rate > float(val.next5_loss_rate.mean())), "bins": merged.to_dict(orient="records")})
    return rows


def main():
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    ledgers = []
    selected_by_cell = {}
    for name in ("forensics_eur", "forensics_xau"):
        path = FORENSICS / name / "trade_ledger.parquet"
        x = pd.read_parquet(path, columns=["strategy_id", "market", "timeframe", "direction", "entry_timestamp", "exit_timestamp", "net_R", "exit_reason", "split"])
        x.entry_timestamp = pd.to_datetime(x.entry_timestamp, utc=True); x.exit_timestamp = pd.to_datetime(x.exit_timestamp, utc=True)
        # The full forensic ledgers contain ~33.5M rows.  The predictability
        # diagnostic is intentionally stratified and bounded: 50 stable,
        # deterministic strategy IDs per market/timeframe cell.  Reading the
        # source ledger is still exact for those selected strategies.
        ids = sorted(x.strategy_id.astype(str).unique())
        chosen = ids[::max(1, len(ids) // 50)][:50]
        selected_by_cell[name] = chosen
        x = x[x.strategy_id.astype(str).isin(chosen)].copy()
        x = _trade_targets(x)
        x = _attach_state(x, "EURUSD" if name == "forensics_eur" else "XAUUSD")
        ledgers.append(x)
    allx = pd.concat(ledgers, ignore_index=True)
    states = _state_report(allx)
    dump("causal_state_predictability.json", {"authority": "DEVELOPMENT_DISCOVERY_VALIDATION_CONFIRMATION", "sample_design": "50 deterministic strategy IDs per market/timeframe cell", "selected_by_cell": selected_by_cell, "states": states, "interpretation": "A state is provisionally useful only when its DEVELOPMENT adverse bin direction is reproduced in VALIDATION; no state is promoted to a trading filter by this diagnostic."})
    # Compact aggregate evidence for the strategy-state versus market-state split.
    split = allx[allx.next5_loss_rate.notna()].copy()
    summary = {"rows": int(len(split)), "strategies": int(split.strategy_id.nunique()), "development": int((split.split.astype(str).str.upper() == "DEVELOPMENT").sum()), "validation": int((split.split.astype(str).str.upper() == "VALIDATION").sum()), "mean_next5_loss_rate": {k: float(v.next5_loss_rate.mean()) for k, v in split.groupby(split.split.astype(str).str.upper())}, "mean_next5_R": {k: float(v.next5_R.mean()) for k, v in split.groupby(split.split.astype(str).str.upper())}, "prior_loss_state": {"corr_next5_loss_rate": float(split[["prior_loss_streak", "next5_loss_rate"]].corr().iloc[0,1]), "corr_next5_R": float(split[["prior_loss_streak", "next5_R"]].corr().iloc[0,1])}, "market_state": {c: float(split[[c, "next5_loss_rate"]].corr().iloc[0,1]) for c in ["ret_1", "ret_4", "ret_16", "vol_16", "atr_pct", "range_pct", "trend_sign", "vol_change"]}}
    dump("loss_state_summary.json", summary)
    dump("performance.json", {"runtime_seconds": time.perf_counter() - started, "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "oos_accesses": 0, "rows": int(len(allx)), "strategies": int(allx.strategy_id.nunique())})
    print(json.dumps({"rows": len(allx), "states": len(states), "runtime_seconds": time.perf_counter() - started, "oos_accesses": 0}, indent=2))


if __name__ == "__main__":
    main()
