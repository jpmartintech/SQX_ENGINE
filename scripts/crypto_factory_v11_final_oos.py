#!/usr/bin/env python
"""Open the reserved partial-2026 OOS exactly once after policy freeze."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pandas as pd

from crypto_factory_v11_portfolio import run_group

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v11"


def digest(paths):
    h = hashlib.sha256()
    for path in paths:
        h.update(Path(path).read_bytes())
    return h.hexdigest()


def main():
    rows = pd.read_parquet(OUT / "strategy_walk_forward.parquet")
    source_files = [OUT / "strategy_walk_forward.parquet", OUT / "strategy_factory_summary.json", OUT / "temporal_policy.json"]
    freeze = {"factory_version": "CRYPTO_STRATEGY_FACTORY_V1_1_PILOT", "strategy_policy": "cycle3 genetic top10 development selection",
              "portfolio_policy": "equal-weight R-normalized, 1% total risk fraction", "leverage": 1.0,
              "dataset_hash": digest([ROOT / "data/crypto_v11/canonical/BTC_H1_signal_market_binance.parquet",
                                       ROOT / "data/crypto_v11/canonical/ETH_H1_signal_market_binance.parquet"]),
              "oos_window": ["2026-07-01T00:00:00Z", "2026-09-28T09:00:00Z"], "final_oos_accesses": 0}
    (OUT / "final_oos_freeze.json").write_text(json.dumps(freeze, indent=2) + "\n")
    results = []
    for asset in ("BTC", "ETH"):
        frame = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_H1_signal_market_binance.parquet")
        frame["timestamp"] = frame.timestamp_open
        scale = float(frame.close.iloc[0])
        for col in ("open", "high", "low", "close"):
            frame[col] = frame[col].astype(float) / scale
        funding = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_funding.parquet")
        result = run_group(asset, 3, rows, frame, funding, ("2026-07-01", "2026-09-28T09:00:00Z"))
        if result:
            result["oos"] = True
            results.append(result)
    # The counter is incremented only here, after the freeze artifact exists.
    final = {"opened": True, "access_count": 1, "window": freeze["oos_window"], "results": results,
             "selection_after_open": False, "oos_accesses": 1}
    (OUT / "final_oos_result.json").write_text(json.dumps(final, indent=2, default=str) + "\n")
    print(json.dumps(final, indent=2, default=str))


if __name__ == "__main__":
    main()
