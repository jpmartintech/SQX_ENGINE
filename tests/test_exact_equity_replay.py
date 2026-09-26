import pandas as pd

from sqx_engine.portfolio_factory.exact_equity import BarEquityReplay


def bars(rows):
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])


def event(**kwargs):
    base = dict(strategy_id="s", market="EURUSD", timeframe="H1", direction="LONG",
                entry_time="2024-01-01T00:00Z", exit_time="2024-01-01T01:00Z",
                entry_price=100.0, stop_price=99.0, target_price=102.0,
                allocated_risk_fraction=.01, contract_value=1.0,
                commission_entry=0.0, commission_exit=0.0, swap=0.0, net_return=.0)
    base.update(kwargs)
    return pd.DataFrame([base])


def test_long_and_short_floating_pnl():
    long_result = BarEquityReplay().replay(event(), bars([
        ("2024-01-01T00:00Z", 100, 101, 99, 101),
        ("2024-01-01T01:00Z", 101, 102, 100, 101),
    ]))
    assert long_result["telemetry"].iloc[0].equity_close == 1.0 + 1.0
    short_result = BarEquityReplay().replay(event(direction="SHORT", stop_price=101, target_price=98), bars([
        ("2024-01-01T00:00Z", 100, 101, 99, 99),
        ("2024-01-01T01:00Z", 99, 100, 98, 99),
    ]))
    assert short_result["telemetry"].iloc[0].equity_close == 2.0


def test_costs_are_not_double_counted():
    result = BarEquityReplay().replay(event(net_return=.10, commission_entry=-.01, commission_exit=-.02), bars([
        ("2024-01-01T00:00Z", 100, 100, 100, 100),
        ("2024-01-01T01:00Z", 100, 100, 100, 100),
    ]))
    assert abs(result["telemetry"].iloc[-1].balance - 1.07) < 1e-12


def test_open_risk_and_daily_equity_are_reported():
    result = BarEquityReplay().replay(event(exit_time="2024-01-01T02:00Z"), bars([
        ("2024-01-01T00:00Z", 100, 100, 99, 99),
        ("2024-01-01T01:00Z", 99, 99, 98, 98),
        ("2024-01-01T02:00Z", 98, 98, 98, 98),
    ]))
    t = result["telemetry"]
    assert "aggregate_initial_open_risk" in t
    assert "daily_loss_floor" in t
    assert t.iloc[0].aggregate_initial_open_risk == .01


def test_same_bar_stop_target_is_counted_ambiguous():
    result = BarEquityReplay().replay(event(), bars([
        ("2024-01-01T00:00Z", 100, 103, 98, 100),
        ("2024-01-01T01:00Z", 100, 100, 100, 100),
    ]))
    assert result["intrabar_ambiguous"] == 1


def test_opposing_positions_are_supported():
    e = pd.concat([event(strategy_id="long"), event(strategy_id="short", direction="SHORT", stop_price=101, target_price=98)], ignore_index=True)
    result = BarEquityReplay().replay(e, bars([
        ("2024-01-01T00:00Z", 100, 101, 99, 100),
        ("2024-01-01T01:00Z", 100, 101, 99, 100),
    ]))
    assert result["positions"] == 2
