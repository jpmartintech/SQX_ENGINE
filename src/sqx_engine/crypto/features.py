"""Causal Crypto-native volume and funding feature construction."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..features.engine import prepare_features


def prepare_crypto_features(data: pd.DataFrame, funding: pd.DataFrame | None = None,
                            variant: str = "PRICE"):
    """Build the existing price bank plus compact causal Crypto features.

    Bar features are available after the bar closes. Funding information is
    carried backward only from settlements at or before the bar open, so a
    signal cannot see a settlement that occurs during its source bar.
    """
    variant = variant.upper()
    if variant not in {"PRICE", "PRICE_VOLUME", "PRICE_FUNDING", "PRICE_VOLUME_FUNDING"}:
        raise ValueError("unknown Crypto information variant")
    out = prepare_features(data, "v1.7")
    if "VOLUME" in variant:
        volume = pd.Series(data.volume.astype(float).to_numpy())
        baseline = volume.rolling(96, min_periods=24).mean().shift(1)
        relative = volume / baseline.replace(0, np.nan)
        out["crypto.volume_relative.96"] = relative.to_numpy()
        out["crypto.volume_roc.16"] = (volume / volume.shift(16).replace(0, np.nan) - 1).to_numpy()
        out["crypto.volume_acceleration.16"] = (relative / relative.shift(16).replace(0, np.nan) - 1).to_numpy()
    if "FUNDING" in variant:
        if funding is None or funding.empty:
            raise ValueError("funding data required for funding variant")
        bars = pd.DataFrame({"timestamp": pd.to_datetime(data.timestamp, utc=True)})
        rates = funding[["timestamp", "funding_rate"]].copy()
        rates["timestamp"] = pd.to_datetime(rates.timestamp, utc=True)
        rates = rates.sort_values("timestamp")
        joined = pd.merge_asof(bars.sort_values("timestamp"), rates, on="timestamp", direction="backward")
        rate = joined.funding_rate.astype(float)
        out["crypto.funding.rate"] = rate.to_numpy()
        out["crypto.funding.change.8"] = rate.diff(8).to_numpy()
        out["crypto.funding.abs"] = rate.abs().to_numpy()
    out.dataset_length = len(data)
    return out
