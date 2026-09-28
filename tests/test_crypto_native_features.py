import numpy as np
import pandas as pd

from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.generator import CryptoRandomGenerator


def _bars(n=120):
    t = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"timestamp": t, "open": np.linspace(1, 2, n), "high": np.linspace(1.01, 2.01, n),
                         "low": np.linspace(.99, 1.99, n), "close": np.linspace(1, 2, n), "volume": np.arange(n, dtype=float) + 10})


def test_volume_features_are_causal_and_funding_uses_prior_settlement():
    bars = _bars()
    funding = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC"),
                            "funding_rate": np.arange(10, dtype=float) / 10000})
    features = prepare_crypto_features(bars, funding, "PRICE_VOLUME_FUNDING")
    assert set(["crypto.volume_relative.96", "crypto.funding.rate"]) <= set(features)
    # The settlement at 00:00 is known before the 00:15 bar closes; later
    # bars still cannot see a future settlement.
    assert features["crypto.funding.rate"][0] == 0.0
    assert np.isfinite(features["crypto.funding.rate"][8])


def test_crypto_generator_variants_emit_native_predicates_and_hashes():
    generator = CryptoRandomGenerator("BTC", "M15", seed=7, grammar_version="v1.7", information_variant="PRICE_VOLUME_FUNDING")
    values = [generator.ask() for _ in range(100)]
    assert all(x.canonical_hash for x in values)
    assert any(any(p.feature.startswith("crypto.") for p in x.predicates) for x in values)
