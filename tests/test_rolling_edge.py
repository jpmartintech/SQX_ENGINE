import pandas as pd
import pytest

from sqx_engine.rolling_edge import (
    activity_metrics, assert_forward_firewall, rolling_cycles, strategy_gate,
)


def test_five_year_one_year_cycles_require_complete_data():
    assert rolling_cycles("2022-11-01", "2026-04-14") == []
    cycles = rolling_cycles("2003-01-01", "2020-12-31")
    assert cycles[0].forward_year == 2008
    assert cycles[-1].forward_year == 2019


def test_partial_forward_is_explicit():
    cycles = rolling_cycles("2018-01-01", "2024-06-01", include_partial=True)
    assert cycles[-1].partial_forward is True
    assert rolling_cycles("2018-01-01", "2024-06-01", include_partial=False)[-1].forward_year == 2023


def test_forward_firewall():
    assert_forward_firewall("2020-12-31", "2021-01-01", ["2020-12-31T23:59Z"])
    with pytest.raises(ValueError):
        assert_forward_firewall("2020-12-31", "2021-01-01", ["2021-01-01T00:00Z"])


def test_strategy_gate_uses_net_pf_and_completed_trades():
    assert strategy_gate(1.151, 251)["pass"]
    assert not strategy_gate(1.30, 250)["pass"]
    assert not strategy_gate(1.149, 1000)["pass"]


def test_activity_metrics_separate_stagnation_and_trade_gaps():
    t = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    m = activity_metrics([1, 1, 2, 2], t, [t[0], t[2]])
    assert m["max_equity_stagnation_days"] is not None
    assert m["median_trade_gap_days"] == 2.0

