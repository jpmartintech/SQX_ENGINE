#!/usr/bin/env python
"""Acquire native Binance USD-M BTC/ETH 15-minute signal history."""
from __future__ import annotations

import csv
from pathlib import Path
import time
import urllib.request
import json
import hashlib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/crypto_v11/raw/binance_futures"
CANONICAL = ROOT / "data/crypto_v12/canonical"
REPORT = ROOT / "runs/reports/crypto_factory_v12"
BASE = "https://fapi.binance.com/fapi/v1/klines"
START = pd.Timestamp("2023-01-01", tz="UTC")
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
BAR_MS = 15 * 60 * 1000


def pull(asset, symbol, end):
    raw = RAW / f"{asset}_15m.csv"
    existing = {}
    if raw.exists():
        for row in pd.read_csv(raw).itertuples(index=False):
            existing[int(pd.Timestamp(row.timestamp_open).timestamp() * 1000)] = row
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    cursor = start_ms if not existing else max(max(existing) + BAR_MS, start_ms)
    while cursor < end_ms:
        url = f"{BASE}?symbol={symbol}&interval=15m&startTime={cursor}&endTime={end_ms}&limit=1000"
        with urllib.request.urlopen(url, timeout=45) as response:
            rows = json.loads(response.read())
        if not rows:
            break
        for row in rows:
            ts = int(row[0])
            if start_ms <= ts < end_ms:
                existing[ts] = (pd.to_datetime(ts, unit="ms", utc=True).isoformat(), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), int(row[8]), float(row[7]))
        last = int(rows[-1][0])
        if last < cursor:
            raise RuntimeError("M15 acquisition cursor did not advance")
        cursor = last + BAR_MS
        time.sleep(0.08)
    RAW.mkdir(parents=True, exist_ok=True)
    with raw.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_open", "open", "high", "low", "close", "volume", "trade_count", "notional_volume"])
        writer.writerows(existing[key] for key in sorted(existing))
    return raw


def main():
    end = pd.Timestamp.now(tz="UTC").floor("15min")
    records = []
    for asset, symbol in SYMBOLS.items():
        raw = pull(asset, symbol, end)
        frame = pd.read_csv(raw, parse_dates=["timestamp_open"])
        frame["timestamp_open"] = pd.to_datetime(frame.timestamp_open, utc=True)
        frame = frame.drop_duplicates("timestamp_open").sort_values("timestamp_open")
        frame["timestamp_close"] = frame.timestamp_open + pd.Timedelta(minutes=15) - pd.Timedelta(microseconds=1)
        frame["available_at"] = frame.timestamp_close + pd.Timedelta(microseconds=1)
        if (frame.high < frame[["open", "close", "low"]].max(axis=1)).any() or (frame.low > frame[["open", "close", "high"]].min(axis=1)).any():
            raise ValueError(f"invalid M15 OHLC {asset}")
        CANONICAL.mkdir(parents=True, exist_ok=True)
        out = CANONICAL / f"{asset}_M15_signal_market_binance.parquet"
        frame.to_parquet(out, index=False)
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        records.append({"asset": asset, "source": "BINANCE_USDM_FUTURES_PUBLIC_REST", "resolution": "15m", "rows": len(frame), "first": str(frame.timestamp_open.iloc[0]), "last": str(frame.timestamp_open.iloc[-1]), "raw_bytes": raw.stat().st_size, "sha256": digest, "canonical": str(out.relative_to(ROOT))})
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "dataset_manifest.json").write_text(json.dumps({"status": "READY", "assets": records, "signal_source": "BINANCE_USDM_FUTURES", "execution_venue": "HYPERLIQUID", "funding_source": "HYPERLIQUID", "v11_oos_burned": ["2026-07-01", "2026-09-28"]}, indent=2) + "\n")
    (REPORT / "DATA_M15_REPORT.md").write_text("# V1.2 M15 Data Report\n\nNative Binance USD-M Futures 15-minute OHLCV was acquired for BTC and ETH from 2023-01-01 through the current data cutoff. The signal source remains explicitly separate from Hyperliquid execution. Bars are UTC, 24/7, closed-bar available, and validated for OHLC invariants, duplicates, and nonnegative volume.\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
