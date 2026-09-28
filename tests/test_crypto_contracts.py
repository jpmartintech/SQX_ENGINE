import pandas as pd
import pytest

from sqx_engine.crypto.data import assert_causal, canonicalize_bars, resample_closed
from sqx_engine.crypto.economics import CryptoEconomicSpecV1, CryptoExecutionCost, funding_pnl, liquidation_price


def bars(n=5):
    start = pd.Timestamp("2024-01-01", tz="UTC")
    opens = pd.date_range(start, periods=n, freq="1min")
    return pd.DataFrame({
        "timestamp_open": opens,
        "timestamp_close": opens + pd.Timedelta(minutes=1) - pd.Timedelta(microseconds=1),
        "open": range(100, 100+n), "high": range(101, 101+n),
        "low": range(99, 99+n), "close": range(100, 100+n), "volume": [1.0]*n,
    })


def test_crypto_bars_are_utc_and_24_7_without_weekend_assumptions():
    frame = canonicalize_bars(bars())
    assert str(frame.timestamp_open.dt.tz) == "UTC"
    assert frame.available_at.iloc[0] == frame.timestamp_close.iloc[0] + pd.Timedelta(microseconds=1)


def test_resample_requires_complete_source_grid():
    assert len(resample_closed(bars(5), 5)) == 1
    incomplete = bars(5).drop(index=2)
    assert resample_closed(incomplete, 5).empty


def test_causal_availability_rejects_unfinished_source():
    with pytest.raises(ValueError):
        assert_causal(["2024-01-01T00:01:00Z"], ["2024-01-01T00:00:59Z"])


def test_crypto_economics_are_distinct_from_forex_swap_semantics():
    spec = CryptoEconomicSpecV1("BTC", leverage=2)
    assert spec.canonical_hash()
    assert CryptoExecutionCost().fee_rate == 0.00045
    assert funding_pnl(1, 50_000, 0.0001, "LONG") == -5
    assert funding_pnl(1, 50_000, 0.0001, "SHORT") == 5
    assert liquidation_price(50_000, "LONG", 2, 0.025) == 26_250
