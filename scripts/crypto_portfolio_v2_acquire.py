#!/usr/bin/env python
"""Acquire/validate V2 multi-asset Binance USD-M signal history.

The signal market is explicitly separate from Hyperliquid execution. Raw
downloads are resumable by timestamp and remain outside Git.
"""
from __future__ import annotations
import csv, hashlib, json, time, urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/crypto_portfolio_v2/raw/binance_futures"
CAN = ROOT / "data/crypto_portfolio_v2/canonical"
OUT = ROOT / "runs/reports/crypto_portfolio_factory_v2"
BASE = "https://fapi.binance.com/fapi/v1/klines"
ASSETS = {"SOL":"SOLUSDT", "XRP":"XRPUSDT", "DOGE":"DOGEUSDT"}
INTERVALS = {"M15": ("15m", 900_000), "H1": ("1h", 3_600_000)}
START = pd.Timestamp("2023-01-01", tz="UTC")

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1<<20), b""): h.update(block)
    return h.hexdigest()

def pull(asset, symbol, tf, interval, step, end):
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{asset}_{tf}.csv"
    existing = {}
    if path.exists():
        old = pd.read_csv(path)
        for r in old.itertuples(index=False): existing[int(pd.Timestamp(r.timestamp_open).timestamp()*1000)] = tuple(r[1:])
    start_ms, end_ms = int(START.timestamp()*1000), int(end.timestamp()*1000)
    cursor = max(start_ms, max(existing)+step if existing else start_ms)
    while cursor < end_ms:
        url = f"{BASE}?symbol={symbol}&interval={interval}&startTime={cursor}&endTime={end_ms}&limit=1000"
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=30) as resp: rows = json.loads(resp.read())
                break
            except Exception:
                if attempt == 4: raise
                time.sleep(2 ** attempt)
        if not rows: break
        for r in rows:
            ts = int(r[0])
            if start_ms <= ts < end_ms:
                existing[ts] = (float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5]),int(r[8]),float(r[7]))
        last = int(rows[-1][0])
        if last < cursor: raise RuntimeError(f"cursor stalled {asset} {tf}")
        cursor = last + step
        time.sleep(0.06)
    with path.open("w", newline="") as f:
        w=csv.writer(f); w.writerow(["timestamp_open","open","high","low","close","volume","trade_count","notional_volume"])
        for ts in sorted(existing): w.writerow([pd.to_datetime(ts, unit="ms", utc=True).isoformat(), *existing[ts]])
    frame=pd.read_csv(path, parse_dates=["timestamp_open"]); frame.timestamp_open=pd.to_datetime(frame.timestamp_open,utc=True)
    minutes=step//60000
    frame["timestamp_close"]=frame.timestamp_open+pd.Timedelta(minutes=minutes)-pd.Timedelta(microseconds=1)
    frame["available_at"]=frame.timestamp_close+pd.Timedelta(microseconds=1)
    if frame.timestamp_open.duplicated().any() or not frame.timestamp_open.is_monotonic_increasing: raise ValueError("duplicate/order")
    if (frame.high < frame[["open","close","low"]].max(axis=1)).any() or (frame.low > frame[["open","close","high"]].min(axis=1)).any(): raise ValueError("OHLC invariant")
    if (frame.volume < 0).any(): raise ValueError("negative volume")
    CAN.mkdir(parents=True, exist_ok=True); out=CAN/f"{asset}_{tf}_signal_market_binance.parquet"; frame.to_parquet(out,index=False)
    return {"asset":asset,"symbol":symbol,"timeframe":tf,"source":"BINANCE_USDM_FUTURES_PUBLIC_REST","execution_venue":"HYPERLIQUID","rows":len(frame),"first":str(frame.timestamp_open.iloc[0]),"last":str(frame.timestamp_open.iloc[-1]),"missing_grid_bars":int(frame.timestamp_open.diff().dropna().gt(pd.Timedelta(milliseconds=step)).sum()),"raw_path":str(path.relative_to(ROOT)),"canonical_path":str(out.relative_to(ROOT)),"sha256":sha(path),"raw_bytes":path.stat().st_size}

def main():
    end=pd.Timestamp.now(tz="UTC").floor("15min"); records=[]
    for asset,symbol in ASSETS.items():
        for tf,(interval,step) in INTERVALS.items():
            try: records.append(pull(asset,symbol,tf,interval,step,end))
            except Exception as exc: records.append({"asset":asset,"timeframe":tf,"status":"FAILED","error":repr(exc)})
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"new_asset_data_manifest.json").write_text(json.dumps({"signal_source":"BINANCE_USDM_FUTURES","execution_venue":"HYPERLIQUID","records":records,"generated_at":str(pd.Timestamp.now(tz="UTC"))},indent=2)+"\n")
    pd.DataFrame(records).to_csv(OUT/"new_asset_data_manifest.csv",index=False)
    print(json.dumps(records,indent=2))
if __name__ == "__main__": main()
