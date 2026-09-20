from pathlib import Path
import pandas as pd

def load_ohlcv(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path); frame.columns = [str(c).lower() for c in frame.columns]
    if "timestamp" not in frame and "datetime" in frame:
        frame = frame.rename(columns={"datetime": "timestamp"})
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing: raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for col in ("open", "high", "low", "close"): frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "spread" not in frame: frame["spread"] = 0.0
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    validate_ohlcv(frame); return frame

def validate_ohlcv(frame):
    if frame.empty or frame.timestamp.duplicated().any() or not frame.timestamp.is_monotonic_increasing: raise ValueError("invalid timestamps")
    if frame[["open", "high", "low", "close"]].isna().any().any(): raise ValueError("OHLC contains NaN")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any(): raise ValueError("non-positive price")
    if (frame.high < frame[["open", "close"]].max(axis=1)).any() or (frame.low > frame[["open", "close"]].min(axis=1)).any(): raise ValueError("invalid OHLC geometry")
