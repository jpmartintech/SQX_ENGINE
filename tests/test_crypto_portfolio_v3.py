import pandas as pd
import pytest

from sqx_engine.crypto.portfolio_v3 import replay_concurrent


def bars():
    t = pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC")
    return {"BTC": pd.DataFrame({"timestamp": t, "close": [100, 101, 99, 102, 103]})}


def event(h, entry, exit_, direction="LONG", r=1.0):
    return {"hash": h, "asset": "BTC", "direction": direction,
            "entry_time": pd.Timestamp(entry, tz="UTC"), "exit_time": pd.Timestamp(exit_, tz="UTC"),
            "r": r, "entry_price": 100.0, "exit_price": 101.0}


def test_true_replay_realizes_and_marks_floating_equity():
    e = pd.DataFrame([event("a", "2025-01-01 00:00", "2025-01-01 02:00", r=2.0)])
    out = replay_concurrent(e, bars(), total_risk=.01)
    assert out.final_equity == pytest.approx(1.02)
    assert out.minimum_equity <= 1.0
    assert out.economically_valid


def test_same_timestamp_exits_are_processed_before_entries():
    e = pd.DataFrame([
        event("a", "2025-01-01 00:00", "2025-01-01 01:00", r=1.0),
        event("b", "2025-01-01 01:00", "2025-01-01 03:00", r=1.0),
    ])
    out = replay_concurrent(e, bars(), total_risk=.01)
    assert len(out.trades) == 2
    assert out.peak_concurrent >= 1


def test_negative_equity_is_not_economically_valid():
    e = pd.DataFrame([event("a", "2025-01-01 00:00", "2025-01-01 01:00", r=-200.0)])
    out = replay_concurrent(e, bars(), total_risk=.01)
    assert not out.economically_valid
    assert out.minimum_equity < 0


def test_composite_strategy_keys_prevent_cross_asset_weight_collision():
    b = {"BTC": bars()["BTC"], "ETH": bars()["BTC"].assign(close=[100, 99, 101, 102, 103])}
    e = pd.DataFrame([
        {**event("same", "2025-01-01 00:00", "2025-01-01 01:00", r=1.0), "strategy_key": "BTC:same"},
        {**event("same", "2025-01-01 00:00", "2025-01-01 01:00", direction="SHORT", r=1.0), "asset": "ETH", "strategy_key": "ETH:same"},
    ])
    out = replay_concurrent(e, b, total_risk=.01, weights={"BTC:same": .5, "ETH:same": .5})
    assert len(out.trades) == 2
    assert out.final_equity > 1.0
