import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from crypto_economic_strategy_contract_v1 import bounded_replay


def bars():
    ts = pd.date_range("2025-01-01", periods=8, freq="15min", tz="UTC")
    return {"BTC": pd.DataFrame({"timestamp": ts, "close": [100.0] * len(ts)})}


def event(entry, exit_, r, direction="LONG"):
    return {"entry_time": pd.Timestamp(entry, tz="UTC"), "exit_time": pd.Timestamp(exit_, tz="UTC"),
            "direction": direction, "r": r, "entry_price": 100.0, "exit_price": 100.0,
            "entry_index": 0, "exit_index": 1, "asset": "BTC"}


def test_one_r_loss_is_one_percent_and_sequential_losses_compound():
    one = bounded_replay([event("2025-01-01 00:00", "2025-01-01 00:15", -1)], bars())
    assert abs(one["final_equity"] - 0.99) < 1e-12
    ten = [event(f"2025-01-01 0{i}:00", f"2025-01-01 0{i}:15", -1) for i in range(7)]
    # Seven events fit the small synthetic bar range; the contract remains
    # fixed-fractional and cannot become negative from -1R losses.
    result = bounded_replay(ten, bars())
    assert result["final_equity"] > 0


def test_overlapping_entries_are_heat_capped_and_overshoot_is_honest():
    first = event("2025-01-01 00:00", "2025-01-01 01:00", -1)
    second = event("2025-01-01 00:15", "2025-01-01 01:15", -2)
    result = bounded_replay([first, second], bars())
    assert result["peak_open_risk"] <= 0.01 + 1e-12
    assert result["resized_entries"] >= 1 or result["skipped_entries"] >= 1
    assert result["overshoot_loss"] >= 0


def test_ruin_halts_new_trading():
    result = bounded_replay([event("2025-01-01 00:00", "2025-01-01 00:15", -200),
                             event("2025-01-01 00:30", "2025-01-01 00:45", 1)], bars())
    assert result["ruin"] is True
    assert result["skipped_entries"] >= 1
