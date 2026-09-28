#!/usr/bin/env python
"""Portfolio walk-forward for frozen PRICE and PRICE_VOLUME libraries."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.strategy import StrategyDefinition

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v12"
RISK = 0.01
COST = 0.0009
CYCLE_WINDOWS = {
    1: ("2024-07-01", "2025-01-01"),
    2: ("2025-01-01", "2025-07-01"),
    3: ("2025-07-01", "2026-01-01"),
    4: ("2026-01-01", "2026-07-01"),
}


def path(asset, timeframe):
    if timeframe == "H1":
        return ROOT / "data/crypto_v11/canonical" / f"{asset}_H1_signal_market_binance.parquet"
    return ROOT / "data/crypto_v12/canonical" / f"{asset}_M15_signal_market_binance.parquet"


def run_group(group, frame, funding, window_override=None):
    row = group.iloc[0]
    idx = pd.DatetimeIndex(frame.timestamp)
    window_start, window_end = CYCLE_WINDOWS[int(row["cycle_id"])] if window_override is None else window_override
    start = int(idx.searchsorted(pd.Timestamp(window_start, tz="UTC")))
    end = int(idx.searchsorted(pd.Timestamp(window_end, tz="UTC")))
    variant = row["variant"]
    evaluator = FastEvaluator(frame, prepare_crypto_features(frame, funding, variant), initial_capital=1.0, spread=COST, engine="numba")
    selected = group.sort_values(["train_expectancy_r", "train_pf", "train_maxdd", "hash"], ascending=[False, False, True, True]).head(10)
    bars = np.zeros(end - start)
    members = []
    for item in selected.itertuples(index=False):
        result = evaluator.evaluate(StrategyDefinition.from_json(item.strategy), start=start, end=end, rich=True)
        one = np.zeros(end - start)
        for trade in result.trades:
            exit_ts = pd.Timestamp(trade["exit_time"])
            exit_ts = exit_ts.tz_localize("UTC") if exit_ts.tzinfo is None else exit_ts.tz_convert("UTC")
            exit_idx = int(idx.searchsorted(exit_ts, side="left")) - start
            entry_ts = pd.Timestamp(trade["entry_time"])
            entry_ts = entry_ts.tz_localize("UTC") if entry_ts.tzinfo is None else entry_ts.tz_convert("UTC")
            fr = funding[(funding.timestamp >= entry_ts) & (funding.timestamp <= exit_ts)]
            risk_price = abs(float(trade["pnl"]) / float(trade["r"])) if abs(float(trade["r"])) > 1e-12 else 0
            entry_i = int(idx.searchsorted(entry_ts, side="left"))
            entry_price = float(frame.close.iloc[min(max(entry_i, 0), len(frame)-1)])
            sign = -1.0 if trade["direction"] == "LONG" else 1.0
            funding_r = sign * float(fr.funding_rate.sum()) * entry_price / max(risk_price, 1e-12)
            if 0 <= exit_idx < len(one):
                one[exit_idx] += (float(trade["r"]) + funding_r) * RISK
        bars += one / max(len(selected), 1)
        members.append({"hash": item.hash, "forward_pf": result.profit_factor, "trades": result.trade_count})
    equity = np.cumprod(1 + bars)
    peaks = np.maximum.accumulate(equity)
    dd = (peaks - equity) / peaks
    return {"asset": row["asset"], "timeframe": row["timeframe"], "cycle_id": int(row["cycle_id"]), "meta_split": row["meta_split"],
            "variant": variant, "strategies": len(selected), "return": float(equity[-1] - 1), "maxdd": float(dd.max()),
            "worst_bar": float(bars.min()), "benchmark": float(frame.close.iloc[end-1] / frame.close.iloc[start] - 1), "members": members}


def main():
    rows = pd.read_parquet(OUT / "strategy_walk_forward.parquet")
    results = []
    for (asset, timeframe, cycle_id, variant), group in rows[rows.variant.isin(["PRICE", "PRICE_VOLUME"])].groupby(["asset", "timeframe", "cycle_id", "variant"]):
        frame = pd.read_parquet(path(asset, timeframe))
        frame["timestamp"] = pd.to_datetime(frame.timestamp_open, utc=True)
        scale = float(frame.close.iloc[0])
        for col in ("open", "high", "low", "close"):
            frame[col] = frame[col].astype(float) / scale
        funding = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_funding.parquet")
        results.append(run_group(group, frame, funding))
    flat = [{k: v for k, v in r.items() if k != "members"} for r in results]
    pd.DataFrame(flat).to_parquet(OUT / "portfolio_walk_forward.parquet", index=False)
    pd.DataFrame(flat).to_parquet(OUT / "portfolio_frontier.parquet", index=False)
    summary = pd.DataFrame(flat).groupby(["variant", "meta_split"]).agg(cycles=("return", "size"), median_return=("return", "median"), positive_rate=("return", lambda x: float((x > 0).mean())), median_maxdd=("maxdd", "median"), median_benchmark=("benchmark", "median")).reset_index()
    (OUT / "portfolio_factory_config.json").write_text(json.dumps({"variants": ["PRICE", "PRICE_VOLUME"], "portfolio_size": 10, "risk_fraction": RISK, "leverage": 1.0, "methods": "top10 equal risk", "exact_r_normalized": True}, indent=2) + "\n")
    (OUT / "portfolio_factory_summary.json").write_text(summary.to_json(orient="records", indent=2) + "\n")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
