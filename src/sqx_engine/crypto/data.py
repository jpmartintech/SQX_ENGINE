"""Canonical UTC Crypto bar and causal availability helpers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

import pandas as pd


BASE_COLUMNS = ("timestamp_open", "timestamp_close", "open", "high", "low", "close", "volume")


def canonicalize_bars(frame: pd.DataFrame, interval: str = "1min") -> pd.DataFrame:
    """Validate and canonicalize completed 24/7 bars without filling gaps."""
    missing = [c for c in BASE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"missing canonical columns: {missing}")
    result = frame.copy()
    for col in ("timestamp_open", "timestamp_close"):
        result[col] = pd.to_datetime(result[col], utc=True)
    if result[list(BASE_COLUMNS)].isna().any().any():
        raise ValueError("canonical bars contain nulls")
    if result.timestamp_open.duplicated().any() or not result.timestamp_open.is_monotonic_increasing:
        raise ValueError("bar opens must be unique and increasing")
    expected = pd.Timedelta(interval)
    if ((result.timestamp_close - result.timestamp_open) != expected - pd.Timedelta(microseconds=1)).all() is False:
        raise ValueError("bar close semantics do not match interval")
    result["available_at"] = result.timestamp_close + pd.Timedelta(microseconds=1)
    return result.reset_index(drop=True)


def assert_causal(feature_available_at: Iterable, decision_at: Iterable) -> None:
    available = pd.to_datetime(list(feature_available_at), utc=True)
    decision = pd.to_datetime(list(decision_at), utc=True)
    if len(available) != len(decision) or (available > decision).any():
        raise ValueError("feature is not available by decision timestamp")


def dataset_hash(frame: pd.DataFrame) -> str:
    raw = frame.to_json(orient="records", date_format="iso", date_unit="us", double_precision=15)
    return hashlib.sha256(raw.encode()).hexdigest()


def resample_closed(frame: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Causally resample complete UTC base bars, retaining no partial bucket."""
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    f = canonicalize_bars(frame)
    if len(f) == 0:
        return f
    f = f.set_index("timestamp_open")
    rule = f"{minutes}min"
    grouped = f.resample(rule, label="left", closed="left")
    out = grouped.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                      close=("close", "last"), volume=("volume", "sum"), count=("open", "count"))
    expected = minutes
    out = out[out["count"] == expected].drop(columns="count").dropna()
    out = out.reset_index()
    out["timestamp_close"] = out.timestamp_open + pd.Timedelta(minutes=minutes) - pd.Timedelta(microseconds=1)
    out["available_at"] = out.timestamp_close + pd.Timedelta(microseconds=1)
    return out
