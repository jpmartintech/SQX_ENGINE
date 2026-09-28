#!/usr/bin/env python
"""Bounded exact-ish normalized portfolio replay for the V1.1 pilot."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from sqx_engine.features.engine import prepare_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v11"
COST = 0.0009
RISK_FRACTION = 0.01


def run_group(asset, cycle_id, rows, frame, funding, window=None):
    group = rows[(rows.asset == asset) & (rows.cycle_id == cycle_id) & (rows.kind == "GENETIC")]
    group = group.sort_values(["train_expectancy_r", "train_pf", "hash"], ascending=[False, False, True]).head(10)
    if group.empty:
        return None
    idx = pd.DatetimeIndex(frame.timestamp)
    window_start = group.forward_start.iloc[0] if window is None else window[0]
    window_end = group.forward_end.iloc[0] if window is None else window[1]
    start = int(idx.searchsorted(pd.Timestamp(window_start, tz="UTC")))
    end = int(idx.searchsorted(pd.Timestamp(window_end, tz="UTC")))
    evaluator = FastEvaluator(frame, prepare_features(frame, "v1.7"), initial_capital=1.0, spread=COST, engine="numba")
    curves = []
    details = []
    for row in group.itertuples(index=False):
        strategy = StrategyDefinition.from_json(row.strategy)
        result = evaluator.evaluate(strategy, start=start, end=end, rich=True)
        # Size the portfolio from the R-normalized ledger, not raw one-unit
        # price PnL. The generic evaluator intentionally has no portfolio
        # notional model; this layer applies bounded total risk explicitly.
        curve = np.zeros(end - start, dtype=float)
        funding_r_total = 0.0
        for trade in result.trades:
            exit_ts = pd.Timestamp(trade["exit_time"])
            exit_ts = exit_ts.tz_localize("UTC") if exit_ts.tzinfo is None else exit_ts.tz_convert("UTC")
            exit_idx = int(idx.searchsorted(exit_ts, side="left")) - start
            entry_ts = pd.Timestamp(trade["entry_time"])
            entry_ts = entry_ts.tz_localize("UTC") if entry_ts.tzinfo is None else entry_ts.tz_convert("UTC")
            funding_rows = funding[(funding.timestamp >= entry_ts) & (funding.timestamp <= exit_ts)]
            risk_price = abs(float(trade["pnl"]) / float(trade["r"])) if abs(float(trade["r"])) > 1e-12 else 0.0
            entry_i = int(idx.searchsorted(entry_ts, side="left"))
            entry_price = float(frame.close.iloc[min(max(entry_i, 0), len(frame) - 1)])
            direction = -1.0 if trade["direction"] == "LONG" else 1.0
            funding_r = direction * float(funding_rows.funding_rate.sum()) * entry_price / max(risk_price, 1e-12)
            if 0 <= exit_idx < len(curve):
                curve[exit_idx] += (float(trade["r"]) + funding_r) * RISK_FRACTION
                funding_r_total += funding_r
        if len(curve) == end - start:
            curves.append(curve)
            details.append({"hash": row.hash, "return": result.return_pct, "pf": result.profit_factor, "trades": result.trade_count,
                            "funding_r": funding_r_total})
    if not curves:
        return None
    portfolio_returns = np.mean(np.vstack(curves), axis=0)
    equity = np.cumprod(1 + portfolio_returns)
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    return {"asset": asset, "cycle_id": int(cycle_id), "meta_split": group.meta_split.iloc[0],
            "strategies": len(curves), "risk_fraction": RISK_FRACTION,
            "portfolio_return": float(equity[-1] - 1),
            "max_drawdown": float(drawdown.max()), "worst_period": float(portfolio_returns.min()),
            "positive_hours": float((portfolio_returns > 0).mean()), "members": details,
            "benchmark_return": float(frame.close.iloc[end - 1] / frame.close.iloc[start] - 1),
            "forward_start": str(window_start), "forward_end": str(window_end)}


def main():
    rows = pd.read_parquet(OUT / "strategy_walk_forward.parquet")
    results = []
    for asset in sorted(rows.asset.unique()):
        frame = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_H1_signal_market_binance.parquet")
        frame["timestamp"] = frame.timestamp_open
        scale = float(frame.close.iloc[0])
        for col in ("open", "high", "low", "close"):
            frame[col] = frame[col].astype(float) / scale
        funding = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_funding.parquet")
        for cycle_id in sorted(rows[rows.asset == asset].cycle_id.unique()):
            result = run_group(asset, cycle_id, rows, frame, funding)
            if result:
                results.append(result)
    flat = [{k: v for k, v in row.items() if k != "members"} for row in results]
    pd.DataFrame(flat).to_parquet(OUT / "portfolio_walk_forward.parquet", index=False)
    dev = [r for r in results if r["meta_split"] == "META_DEVELOPMENT"]
    val = [r for r in results if r["meta_split"] == "META_VALIDATION"]
    summary = {"portfolio_method": "top10_genetic_equal_weight_normalized", "leverage": 1.0,
               "rows": len(results), "development": dev, "validation": val,
               "development_positive": sum(r["portfolio_return"] > 0 for r in dev),
               "validation_positive": sum(r["portfolio_return"] > 0 for r in val), "oos_accesses": 0}
    (OUT / "portfolio_factory_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (OUT / "portfolio_frontier.parquet").write_bytes((OUT / "portfolio_walk_forward.parquet").read_bytes())
    pd.DataFrame([{"status": "NOT_RUN", "reason": "OOS validation boundary failed", "leverage": None}]).to_parquet(OUT / "leverage_frontier.parquet", index=False)
    print(json.dumps({"rows": len(results), "development": dev, "validation": val}, indent=2, default=str))


if __name__ == "__main__":
    main()
