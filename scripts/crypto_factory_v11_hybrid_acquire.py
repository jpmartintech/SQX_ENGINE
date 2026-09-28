#!/usr/bin/env python
"""Acquire the V1.1 hybrid signal dataset.

Signal market: Binance USD-M perpetual OHLCV (public REST).
Execution venue: Hyperliquid perpetuals.
Funding: Hyperliquid realized funding, downloaded separately by the
Hyperliquid acquisition supervisor.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/crypto_v11/raw/binance_futures"
CANONICAL = ROOT / "data/crypto_v11/canonical"
REPORT = ROOT / "runs/reports/crypto_factory_v11/data_acquisition"
BASE = "https://fapi.binance.com/fapi/v1/klines"
START = pd.Timestamp("2023-01-01", tz="UTC")
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
HOUR_MS = 3_600_000
LIMIT = 1_000


def request(symbol: str, start: int, end: int):
    url = f"{BASE}?symbol={symbol}&interval=1h&startTime={start}&endTime={end}&limit={LIMIT}"
    with urllib.request.urlopen(url, timeout=45) as response:
        return json.loads(response.read())


def pull(asset: str, symbol: str, end: pd.Timestamp) -> Path:
    path = RAW / f"{asset}_1h.csv"
    existing = {}
    if path.exists():
        for row in pd.read_csv(path).itertuples(index=False):
            existing[int(pd.Timestamp(row.timestamp_open).timestamp() * 1000)] = row
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    cursor = start_ms if not existing else max(max(existing) + HOUR_MS, start_ms)
    while cursor < end_ms:
        rows = request(symbol, cursor, end_ms)
        if not rows:
            break
        for row in rows:
            ts = int(row[0])
            if start_ms <= ts < end_ms:
                existing[ts] = (pd.to_datetime(ts, unit="ms", utc=True).isoformat(),
                                float(row[1]), float(row[2]), float(row[3]), float(row[4]),
                                float(row[5]), int(row[8]), float(row[7]))
        last = int(rows[-1][0])
        if last < cursor:
            raise RuntimeError("Binance cursor did not advance")
        cursor = last + HOUR_MS
        time.sleep(0.08)
    RAW.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_open", "open", "high", "low", "close", "volume", "trade_count", "notional_volume"])
        writer.writerows(existing[key] for key in sorted(existing))
    return path


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    end = pd.Timestamp.now(tz="UTC").floor("h")
    rows = []
    for asset, symbol in SYMBOLS.items():
        raw = pull(asset, symbol, end)
        frame = pd.read_csv(raw, parse_dates=["timestamp_open"])
        frame["timestamp_open"] = pd.to_datetime(frame.timestamp_open, utc=True)
        frame = frame.drop_duplicates("timestamp_open").sort_values("timestamp_open")
        frame["timestamp_close"] = frame.timestamp_open + pd.Timedelta(hours=1) - pd.Timedelta(microseconds=1)
        frame["available_at"] = frame.timestamp_close + pd.Timedelta(microseconds=1)
        if (frame.high < frame[["open", "close", "low"]].max(axis=1)).any() or (frame.low > frame[["open", "close", "high"]].min(axis=1)).any():
            raise ValueError(f"invalid OHLC {asset}")
        out = CANONICAL / f"{asset}_H1_signal_market_binance.parquet"
        CANONICAL.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(out, index=False)
        rows.append({"asset": asset, "field": "OHLCV", "source": "BINANCE_USDM_FUTURES_PUBLIC_REST",
                     "signal_market": True, "execution_venue": "HYPERLIQUID", "path": str(raw.relative_to(ROOT)),
                     "canonical_path": str(out.relative_to(ROOT)), "rows": len(frame),
                     "first": str(frame.timestamp_open.iloc[0]), "last": str(frame.timestamp_open.iloc[-1]),
                     "bytes": raw.stat().st_size, "sha256": sha(raw)})
    REPORT.mkdir(parents=True, exist_ok=True)
    old = json.loads((REPORT / "download_manifest.json").read_text()) if (REPORT / "download_manifest.json").exists() else []
    (REPORT / "download_manifest.json").write_text(json.dumps(old + rows, indent=2) + "\n")
    (REPORT / "source_comparison.json").write_text(json.dumps({
        "official_hyperliquid_rest": {"status": "selected_for_funding_and_recent_overlap"},
        "binance_usdm_futures": {"status": "selected_for_signal_history", "reason": "Hyperliquid historical candle endpoint returned no pre-2026 windows", "not_hyperliquid_execution": True},
        "hybrid_contract": {"signal_market_source": "BINANCE_USDM_FUTURES", "execution_venue": "HYPERLIQUID", "funding_source": "HYPERLIQUID_PUBLIC_REST"}
    }, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
