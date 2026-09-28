#!/usr/bin/env python
"""Run frozen equal-budget V1.2 information variants across later cycles."""
from __future__ import annotations

import json
from pathlib import Path
import time
import pandas as pd

from crypto_factory_v12_ablation import load, bounds, run_search, ASSETS, TIMEFRAMES, VARIANTS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v12"
WALK_BUDGET = 2_000


def main():
    started = time.perf_counter()
    # Frozen before validation: 18m manufacture -> 6m forward, six-month step.
    cycles = [
        (1, "2023-01-01", "2024-07-01", "2024-07-01", "2025-01-01", "META_DEVELOPMENT"),
        (2, "2023-07-01", "2025-01-01", "2025-01-01", "2025-07-01", "META_DEVELOPMENT"),
        (3, "2024-01-01", "2025-07-01", "2025-07-01", "2026-01-01", "META_VALIDATION"),
        (4, "2024-07-01", "2026-01-01", "2026-01-01", "2026-07-01", "META_VALIDATION"),
    ]
    rows = []
    for asset in ASSETS:
        funding = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_funding.parquet")
        for timeframe in TIMEFRAMES:
            frame = load(asset, timeframe)
            for cycle_id, train_a, train_b, forward_a, forward_b, split in cycles:
                train_start, train_end = bounds(frame, train_a, train_b)
                forward_start, forward_end = bounds(frame, forward_a, forward_b)
                for variant_i, variant in enumerate(VARIANTS):
                    _, forward = run_search(frame, funding, variant, train_start, train_end, forward_start, forward_end,
                                            WALK_BUDGET, 31000 + cycle_id * 100 + variant_i + (0 if asset == "BTC" else 50), False, asset, timeframe)
                    rows.extend({"asset": asset, "timeframe": timeframe, "cycle_id": cycle_id, "meta_split": split,
                                 "variant": variant, "budget": WALK_BUDGET, **r} for r in forward)
    frame = pd.DataFrame(rows)
    frame.to_parquet(OUT / "strategy_walk_forward.parquet", index=False)
    stats = frame.groupby(["variant", "meta_split"]).agg(records=("hash", "size"), median_forward_pf=("forward_pf", "median"), median_forward_expectancy=("forward_expectancy_r", "median"), positive_record_rate=("forward_return", lambda x: float((x > 0).mean())), median_maxdd=("forward_maxdd", "median")).reset_index()
    stats.to_json(OUT / "strategy_factory_summary.json", orient="records", indent=2)
    (OUT / "strategy_gate.json").write_text(json.dumps({"train_pf": ">1.0", "train_trades": ">=20", "selection": "top50 by frozen train expectancy/PF/MaxDD/hash", "frozen_before_validation": True}, indent=2) + "\n")
    (OUT / "meta_split.json").write_text(json.dumps({"development_cycles": [1, 2], "validation_cycles": [3, 4], "burned_v11_period": ["2026-07-01", "2026-09-28"], "oos_accesses_v12": 0}, indent=2) + "\n")
    (OUT / "temporal_policy.json").write_text(json.dumps({"manufacturing_months": 18, "forward_months": 6, "step_months": 6, "frozen": True}, indent=2) + "\n")
    print(stats.to_string(index=False))
    print(json.dumps({"rows": len(frame), "runtime_seconds": time.perf_counter() - started}, indent=2))


if __name__ == "__main__":
    main()
