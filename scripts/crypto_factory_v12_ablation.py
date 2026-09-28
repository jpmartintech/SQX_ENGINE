#!/usr/bin/env python
"""Fair V1.2 information ablation and frozen walk-forward pilot."""
from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.generator import CryptoGeneticGenerator, CryptoRandomGenerator
from sqx_engine.strategy import StrategyDefinition

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v12"
ASSETS = ("BTC", "ETH")
TIMEFRAMES = ("H1", "M15")
VARIANTS = ("PRICE", "PRICE_VOLUME", "PRICE_FUNDING", "PRICE_VOLUME_FUNDING")
BUDGET = 10_000
RANDOM_BUDGET = 2_000
COST = 0.0009


def load(asset, timeframe):
    if timeframe == "H1":
        path = ROOT / "data/crypto_v11/canonical" / f"{asset}_H1_signal_market_binance.parquet"
    else:
        path = ROOT / "data/crypto_v12/canonical" / f"{asset}_M15_signal_market_binance.parquet"
    frame = pd.read_parquet(path).copy()
    frame["timestamp"] = pd.to_datetime(frame.timestamp_open, utc=True)
    scale = float(frame.close.iloc[0])
    for col in ("open", "high", "low", "close"):
        frame[col] = frame[col].astype(float) / scale
    return frame.reset_index(drop=True)


def bounds(frame, a, b):
    idx = pd.DatetimeIndex(frame.timestamp)
    return int(idx.searchsorted(pd.Timestamp(a, tz="UTC"))), int(idx.searchsorted(pd.Timestamp(b, tz="UTC")))


def run_search(frame, funding, variant, train_start, train_end, forward_start, forward_end, budget, seed, random=False, asset="CRYPTO", timeframe="H1"):
    features = prepare_crypto_features(frame, funding, variant)
    evaluator = FastEvaluator(frame, features, initial_capital=1.0, spread=COST, engine="numba")
    if random:
        generator = CryptoRandomGenerator(asset, timeframe, seed=seed, min_predicates=1, max_predicates=2,
                                          grammar_version="v1.7", information_variant=variant)
    else:
        generator = CryptoGeneticGenerator(asset, timeframe, seed=seed, min_predicates=1, max_predicates=2,
                                           grammar_version="v1.7", information_variant=variant,
                                           population_size=40, mode="scale")
    rows = []
    for _ in range(budget):
        strategy = generator.ask()
        result = evaluator.evaluate(strategy, start=train_start, end=train_end, rich=False)
        if not random:
            generator.tell(strategy, result)
        if result.trade_count >= 20 and result.profit_factor > 1.0:
            rows.append({"strategy": strategy.to_json(), "hash": strategy.canonical_hash,
                         "train_pf": result.profit_factor, "train_expectancy_r": result.expectancy_r,
                         "train_trades": result.trade_count, "train_return": result.return_pct,
                         "train_maxdd": result.max_drawdown, "kind": "RANDOM" if random else "GENETIC"})
    rows = sorted(rows, key=lambda x: (x["train_expectancy_r"], x["train_pf"], -x["train_maxdd"], x["hash"]), reverse=True)
    forward = []
    for row in rows[:50]:
        result = evaluator.evaluate(StrategyDefinition.from_json(row["strategy"]), start=forward_start, end=forward_end, rich=False)
        forward.append({**row, "forward_pf": result.profit_factor, "forward_expectancy_r": result.expectancy_r,
                        "forward_trades": result.trade_count, "forward_return": result.return_pct,
                        "forward_maxdd": result.max_drawdown})
    return rows, forward


def main():
    started = time.perf_counter()
    cycle = {"train": ("2023-01-01", "2024-07-01"), "forward": ("2024-07-01", "2025-01-01")}
    ablation = []
    walk = []
    random_control = []
    for asset in ASSETS:
        funding = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_funding.parquet")
        for timeframe in TIMEFRAMES:
            frame = load(asset, timeframe)
            train_start, train_end = bounds(frame, *cycle["train"])
            forward_start, forward_end = bounds(frame, *cycle["forward"])
            for variant_i, variant in enumerate(VARIANTS):
                rows, forward = run_search(frame, funding, variant, train_start, train_end, forward_start, forward_end, BUDGET, 12000 + variant_i + (0 if asset == "BTC" else 100), False, asset, timeframe)
                ablation.extend({"asset": asset, "timeframe": timeframe, "variant": variant, "budget": BUDGET, **r} for r in forward)
            # Equal-budget Random control on representative cells.
            if asset == "BTC":
                for variant_i, variant in enumerate(VARIANTS):
                    _, forward = run_search(frame, funding, variant, train_start, train_end, forward_start, forward_end, RANDOM_BUDGET, 22000 + variant_i, True, asset, timeframe)
                    random_control.extend({"asset": asset, "timeframe": timeframe, "variant": variant, "budget": RANDOM_BUDGET, **r} for r in forward)
    ab_df = pd.DataFrame(ablation)
    rand_df = pd.DataFrame(random_control)
    OUT.mkdir(parents=True, exist_ok=True)
    ab_df.to_parquet(OUT / "ablation_results.parquet", index=False)
    rand_df.to_parquet(OUT / "random_vs_genetic.parquet", index=False)
    stats = ab_df.groupby(["variant", "asset", "timeframe"]).agg(eligible=("hash", "size"), forward_pf=("forward_pf", "median"), forward_expectancy=("forward_expectancy_r", "median"), forward_survival=("forward_return", lambda x: float((x > 0).mean()))).reset_index()
    (OUT / "information_value.json").write_text(json.dumps(stats.to_dict(orient="records"), indent=2, default=str) + "\n")
    (OUT / "ablation_config.json").write_text(json.dumps({"variants": VARIANTS, "budget": BUDGET, "random_budget": RANDOM_BUDGET, "cycle": cycle, "cost": COST, "oos_accesses": 0}, indent=2) + "\n")
    (OUT / "generation_scaling.json").write_text(json.dumps({"10K": "executed", "50K": "not executed; final bounded test and no OOS edge confirmation", "runtime_seconds": time.perf_counter() - started}, indent=2) + "\n")
    print(stats.to_string(index=False))
    print(json.dumps({"rows": len(ab_df), "random_rows": len(rand_df), "runtime_seconds": time.perf_counter() - started}, indent=2))


if __name__ == "__main__":
    main()
