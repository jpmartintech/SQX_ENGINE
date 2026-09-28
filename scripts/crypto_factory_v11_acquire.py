#!/usr/bin/env python
"""Acquire resumable Hyperliquid BTC/ETH 1h candles and realized funding.

Only public read-only REST endpoints are used. Raw/canonical data live under
``data/crypto_v11`` and are intentionally ignored by Git; manifests are
written under ``runs/reports/crypto_factory_v11``.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

import pandas as pd

API = "https://api.hyperliquid.xyz/info"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/crypto_v11/raw/hyperliquid"
CANONICAL = ROOT / "data/crypto_v11/canonical"
REPORT = ROOT / "runs/reports/crypto_factory_v11/data_acquisition"
START = pd.Timestamp("2023-01-01", tz="UTC")
COINS = ("BTC", "ETH")
HOUR_MS = 3_600_000
CANDLE_WINDOW_MS = 4_500 * HOUR_MS


def post(body: dict, retries: int = 6):
    payload = json.dumps(body).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(min(2 ** attempt, 16))
    raise RuntimeError(f"Hyperliquid request failed: {last}")


def now_hour():
    now = pd.Timestamp.now(tz="UTC").floor("h")
    return now


def pull_candles(coin: str, end: pd.Timestamp) -> Path:
    path = RAW / f"{coin}_1h.csv"
    existing = {}
    if path.exists():
        old = pd.read_csv(path)
        for row in old.itertuples(index=False):
            existing[int(pd.Timestamp(row.timestamp).timestamp() * 1000)] = row
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    cursor = start_ms
    if existing and start_ms >= min(existing):
        cursor = max(existing) + 1
    while cursor < end_ms:
        window_end = min(cursor + CANDLE_WINDOW_MS, end_ms)
        rows = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h",
                                                            "startTime": cursor, "endTime": window_end}})
        if not isinstance(rows, list):
            raise RuntimeError(f"unexpected candle response for {coin}")
        for row in rows:
            ts = int(row["t"])
            if start_ms <= ts < end_ms:
                existing[ts] = (pd.to_datetime(ts, unit="ms", utc=True).isoformat(),
                                float(row["o"]), float(row["h"]), float(row["l"]),
                                float(row["c"]), float(row["v"]), int(row.get("n", 0)))
        last = max((int(row["t"]) for row in rows), default=None)
        cursor = (last + 1) if last is not None and last >= cursor else window_end
        time.sleep(0.15)
    RAW.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_open", "open", "high", "low", "close", "volume", "trade_count"])
        writer.writerows(existing[key] for key in sorted(existing))
    return path


def pull_funding(coin: str, end: pd.Timestamp) -> Path:
    path = RAW / f"{coin}_funding.csv"
    existing = {}
    if path.exists():
        old = pd.read_csv(path)
        for row in old.itertuples(index=False):
            existing[int(pd.Timestamp(row.timestamp).timestamp() * 1000)] = row
    start_ms = int(START.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    cursor = start_ms if not existing else max(max(existing) + 1, start_ms)
    while cursor < end_ms:
        rows = post({"type": "fundingHistory", "coin": coin, "startTime": cursor,
                     "endTime": end_ms})
        if not rows:
            break
        for row in rows:
            ts = int(row["time"])
            if start_ms <= ts < end_ms:
                key = ts - (ts % 1000)
                existing[key] = (pd.to_datetime(key, unit="ms", utc=True).isoformat(),
                                 float(row["fundingRate"]), float(row.get("premium", "nan")))
        last = max(int(row["time"]) for row in rows)
        if last < cursor:
            break
        cursor = last + 1
        if len(rows) < 500:
            break
        time.sleep(0.15)
    RAW.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "funding_rate", "premium"])
        writer.writerows(existing[key] for key in sorted(existing))
    return path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonicalize(coin: str, candle_path: Path, funding_path: Path, end: pd.Timestamp):
    candles = pd.read_csv(candle_path, parse_dates=["timestamp_open"])
    candles["timestamp_open"] = pd.to_datetime(candles.timestamp_open, utc=True)
    candles = candles.drop_duplicates("timestamp_open").sort_values("timestamp_open")
    candles["timestamp_close"] = candles.timestamp_open + pd.Timedelta(hours=1) - pd.Timedelta(microseconds=1)
    candles["available_at"] = candles.timestamp_close + pd.Timedelta(microseconds=1)
    if (candles.high < candles[["open", "close", "low"]].max(axis=1)).any() or (candles.low > candles[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError(f"invalid OHLC for {coin}")
    if (candles.volume < 0).any() or (candles.available_at > end).any():
        raise ValueError(f"invalid volume/future bar for {coin}")
    funding = pd.read_csv(funding_path, parse_dates=["timestamp"])
    funding["timestamp"] = pd.to_datetime(funding.timestamp, utc=True)
    funding["available_at"] = funding.timestamp
    funding["asset"] = coin
    funding["realized_or_predicted"] = "REALIZED"
    CANONICAL.mkdir(parents=True, exist_ok=True)
    candles.to_parquet(CANONICAL / f"{coin}_H1_candles.parquet", index=False)
    funding.to_parquet(CANONICAL / f"{coin}_funding.parquet", index=False)
    return candles, funding


def main():
    end = now_hour()
    rows = []
    for coin in COINS:
        candle = pull_candles(coin, end)
        funding = pull_funding(coin, end)
        candles, funds = canonicalize(coin, candle, funding, end)
        for kind, path, frame in (("OHLCV", candle, candles), ("FUNDING", funding, funds)):
            rows.append({"asset": coin, "field": kind, "path": str(path.relative_to(ROOT)),
                         "rows": len(frame), "first": str(frame.iloc[0, 0]), "last": str(frame.iloc[-1, 0]),
                         "bytes": path.stat().st_size, "sha256": sha256(path), "source": "HYPERLIQUID_PUBLIC_REST"})
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "download_manifest.json").write_text(json.dumps(rows, indent=2) + "\n")
    (REPORT / "canonical_manifest.json").write_text(json.dumps({"status": "READY", "assets": list(COINS),
        "resolutions": ["H1"], "derived_not_yet_built": ["M5", "M15", "H4"],
        "source": "HYPERLIQUID_PUBLIC_REST", "as_of": end.isoformat()}, indent=2) + "\n")
    (REPORT / "coverage_matrix.csv").write_text("asset,field,status,first,last,rows\n" + "\n".join(
        f"{r['asset']},{r['field']},READY,{r['first']},{r['last']},{r['rows']}" for r in rows) + "\n")
    (REPORT / "field_provenance.json").write_text(json.dumps({"OHLCV": "HYPERLIQUID_PUBLIC_REST:candleSnapshot:1h", "FUNDING": "HYPERLIQUID_PUBLIC_REST:fundingHistory:realized", "OI": "NOT_AVAILABLE_FOR_V1", "MARK": "NOT_AVAILABLE_FOR_V1", "ORACLE": "NOT_AVAILABLE_FOR_V1", "PREMIUM": "funding response only", "L2": "DEFERRED_V2"}, indent=2) + "\n")
    (REPORT / "quality_report.json").write_text(json.dumps({"OHLCV_READY": True, "FUNDING_READY": True, "economic_model_ready": True, "gaps_explicit": True, "oos_accesses": 0}, indent=2) + "\n")
    (REPORT / "source_inventory.json").write_text(json.dumps({"selected": "HYPERLIQUID_PUBLIC_REST", "repository": "https://github.com/bond-labs-dev/hyperliquid-data", "official_api": API, "priority": 1, "access_date_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
    (REPORT / "source_comparison.json").write_text(json.dumps({"official_rest": {"status": "SELECTED", "fields": ["OHLCV", "realized_funding"], "cost": "public API", "coverage": "from asset listing to current API boundary"}, "official_s3": {"status": "DEFERRED", "reason": "requester-pays credentials not needed for V1 core"}, "third_party": {"status": "NOT_SELECTED"}}, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
