import json
from pathlib import Path

import pandas as pd


def test_v11_hybrid_provenance_keeps_signal_and_execution_venues_distinct():
    path = Path("runs/reports/crypto_factory_v11/data_acquisition/source_comparison.json")
    if not path.exists():
        return
    data = json.loads(path.read_text())
    assert data["hybrid_contract"]["signal_market_source"] == "BINANCE_USDM_FUTURES"
    assert data["hybrid_contract"]["execution_venue"] == "HYPERLIQUID"
    assert data["binance_usdm_futures"]["not_hyperliquid_execution"] is True


def test_v11_canonical_signal_bars_have_causal_utc_availability():
    path = Path("data/crypto_v11/canonical/BTC_H1_signal_market_binance.parquet")
    if not path.exists():
        return
    frame = pd.read_parquet(path)
    assert str(frame.timestamp_open.dt.tz) == "UTC"
    assert (frame.available_at > frame.timestamp_open).all()
    assert (frame.high >= frame[["open", "close", "low"]].max(axis=1)).all()
    assert (frame.low <= frame[["open", "close", "high"]].min(axis=1)).all()
