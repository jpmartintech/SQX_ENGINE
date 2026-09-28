#!/usr/bin/env python
"""Bounded V1.1 price/volume hybrid discovery and walk-forward pilot.

This is deliberately a small, reproducible factory pilot.  It uses the
existing causal grammar/evaluator and keeps Hyperliquid funding as a separate
economic field; signal candles are explicitly Binance Futures history.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from sqx_engine.features.engine import prepare_features
from sqx_engine.generators import GeneticGenerator, RandomGenerator
from sqx_engine.backtest.fast import FastEvaluator

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/crypto_v11/canonical"
OUT = ROOT / "runs/reports/crypto_factory_v11"
ASSETS = ("BTC", "ETH")
BUDGET = 500
COST = 0.0009  # conservative round-trip normalized fee+slippage proxy


def load(asset):
    frame = pd.read_parquet(DATA / f"{asset}_H1_signal_market_binance.parquet").copy()
    frame["timestamp"] = frame["timestamp_open"]
    scale = float(frame.close.iloc[0])
    for col in ("open", "high", "low", "close"):
        frame[col] = frame[col].astype(float) / scale
    return frame.reset_index(drop=True)


def eval_population(frame, start, end, seed, kind):
    features = prepare_features(frame, "v1.7")
    evaluator = FastEvaluator(frame, features, initial_capital=1.0, spread=COST, slippage=0.0, engine="numba")
    if kind == "RANDOM":
        generator = RandomGenerator("CRYPTO", "H1", seed=seed, min_predicates=1, max_predicates=2, grammar_version="v1.7")
    else:
        generator = GeneticGenerator("CRYPTO", "H1", seed=seed, min_predicates=1, max_predicates=2,
                                     grammar_version="v1.7", population_size=40, mode="scale")
    rows = []
    for i in range(BUDGET):
        strategy = generator.ask()
        result = evaluator.evaluate(strategy, start=start, end=end, rich=False)
        if kind == "GENETIC":
            generator.tell(strategy, result)
        rows.append({"kind": kind, "seed": seed, "strategy": strategy.to_json(), "hash": strategy.canonical_hash,
                     "train_pf": result.profit_factor, "train_expectancy_r": result.expectancy_r,
                     "train_trades": result.trade_count, "train_return": result.return_pct,
                     "train_maxdd": result.max_drawdown, "train_sharpe": result.sharpe})
    return rows, generator, evaluator


def evaluate_forward(frame, rows, start, end):
    features = prepare_features(frame, "v1.7")
    evaluator = FastEvaluator(frame, features, initial_capital=1.0, spread=COST, slippage=0.0, engine="numba")
    out = []
    for row in rows:
        from sqx_engine.strategy import StrategyDefinition
        strategy = StrategyDefinition.from_json(row["strategy"])
        result = evaluator.evaluate(strategy, start=start, end=end, rich=False)
        out.append({**row, "forward_pf": result.profit_factor, "forward_expectancy_r": result.expectancy_r,
                    "forward_trades": result.trade_count, "forward_return": result.return_pct,
                    "forward_maxdd": result.max_drawdown, "forward_sharpe": result.sharpe})
    return out


def cycle(asset, frame, train_start, train_end, forward_start, forward_end, cycle_id):
    rows = []
    for kind, seed in (("RANDOM", 1101 + cycle_id), ("GENETIC", 2101 + cycle_id)):
        generated, generator, evaluator = eval_population(frame, train_start, train_end, seed, kind)
        # Frozen development selection: enough trades, positive net PF, and a
        # small bounded top slice. This is not a final production gate.
        selected = sorted((r for r in generated if r["train_trades"] >= 20 and r["train_pf"] > 1.0),
                          key=lambda r: (r["train_expectancy_r"], r["train_pf"], -r["train_maxdd"], r["hash"]), reverse=True)[:30]
        rows.extend(evaluate_forward(frame, selected, forward_start, forward_end))
    for row in rows:
        row.update({"asset": asset, "cycle_id": cycle_id, "train_start": str(frame.timestamp.iloc[train_start]),
                    "train_end": str(frame.timestamp.iloc[train_end - 1]), "forward_start": str(frame.timestamp.iloc[forward_start]),
                    "forward_end": str(frame.timestamp.iloc[forward_end - 1])})
    return rows


def main():
    started = time.perf_counter()
    all_rows = []
    cycle_specs = [
        (1, "2023-01-01", "2025-01-01", "2025-01-01", "2025-07-01", "META_DEVELOPMENT"),
        (2, "2023-07-01", "2025-07-01", "2025-07-01", "2026-01-01", "META_DEVELOPMENT"),
        (3, "2024-01-01", "2026-01-01", "2026-01-01", "2026-07-01", "META_VALIDATION"),
    ]
    manifests = []
    for asset in ASSETS:
        frame = load(asset)
        for cycle_id, train_a, train_b, fwd_a, fwd_b, split in cycle_specs:
            idx = pd.DatetimeIndex(frame.timestamp)
            train_start = int(idx.searchsorted(pd.Timestamp(train_a, tz="UTC"), side="left"))
            train_end = int(idx.searchsorted(pd.Timestamp(train_b, tz="UTC"), side="left"))
            forward_start = int(idx.searchsorted(pd.Timestamp(fwd_a, tz="UTC"), side="left"))
            forward_end = int(idx.searchsorted(pd.Timestamp(fwd_b, tz="UTC"), side="left"))
            if forward_end <= forward_start or train_end <= train_start:
                continue
            rows = cycle(asset, frame, train_start, train_end, forward_start, forward_end, cycle_id)
            for row in rows:
                row["meta_split"] = split
            all_rows.extend(rows)
            manifests.append({"asset": asset, "cycle_id": cycle_id, "meta_split": split,
                              "train_start": train_a, "train_end": train_b, "forward_start": fwd_a, "forward_end": fwd_b,
                              "strategies_evaluated": len(rows)})
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_parquet(OUT / "strategy_walk_forward.parquet", index=False)
    summary = {
        "factory_version": "CRYPTO_STRATEGY_FACTORY_V1_1_PILOT",
        "signal_source": "BINANCE_USDM_FUTURES",
        "execution_venue": "HYPERLIQUID",
        "funding_source": "HYPERLIQUID_REALIZED_FUNDING",
        "assets": list(ASSETS), "timeframe": "H1", "budget_per_kind_asset_cycle": BUDGET,
        "cost_proxy_round_trip": COST, "cycles": manifests,
        "rows": len(all_rows),
        "development_positive_forward": int(sum(r["forward_return"] > 0 for r in all_rows if r["meta_split"] == "META_DEVELOPMENT")),
        "development_forward_count": int(sum(r["meta_split"] == "META_DEVELOPMENT" for r in all_rows)),
        "validation_positive_forward": int(sum(r["forward_return"] > 0 for r in all_rows if r["meta_split"] == "META_VALIDATION")),
        "validation_forward_count": int(sum(r["meta_split"] == "META_VALIDATION" for r in all_rows)),
        "runtime_seconds": time.perf_counter() - started,
        "oos_accesses": 0,
    }
    (OUT / "strategy_factory_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    (OUT / "strategy_gate.json").write_text(json.dumps({"status": "PILOT_ONLY", "train_pf": ">1.0", "train_trades": ">=20", "final_gate_frozen": False}, indent=2) + "\n")
    (OUT / "temporal_policy.json").write_text(json.dumps({"manufacturing": "2 years", "forward": "6 months", "step": "6 months", "meta_development_cycles": [1, 2], "meta_validation_cycles": [3], "final_oos_opened": False}, indent=2) + "\n")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
