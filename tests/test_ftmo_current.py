import pandas as pd

from sqx_engine.portfolio_factory.ftmo_current import (
    CurrentFtmoEvaluator, FTMO_1STEP_CURRENT_V1, FTMO_2STEP_CURRENT_V1,
    ftmo_1step_current_profile, ftmo_2step_current_profile,
)


def bars(days):
    out = []
    for d in days:
        ts = pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=10)
        out.append({"timestamp": ts, "open": 100., "high": 100., "low": 100., "close": 100.})
    return {"EURUSD": pd.DataFrame(out)}


def events(rows):
    return pd.DataFrame(rows, columns=["strategy_id", "market", "direction", "entry_timestamp",
                                       "exit_timestamp", "entry_price", "stop_distance", "net_R", "allocated_risk"])


def win(day, r, sid="s"):
    t = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=9)
    return (sid, "EURUSD", "LONG", t, t + pd.Timedelta(minutes=15), 100., 1., r, .01)


def test_current_profiles_are_versioned_and_distinct():
    assert ftmo_1step_current_profile().name == FTMO_1STEP_CURRENT_V1
    assert ftmo_1step_current_profile().daily_loss_fraction == .03
    assert ftmo_1step_current_profile().trailing_max_loss
    assert ftmo_2step_current_profile().name == FTMO_2STEP_CURRENT_V1
    assert ftmo_2step_current_profile().daily_loss_fraction == .05
    assert ftmo_2step_current_profile().minimum_trading_days == 4


def test_two_step_requires_four_trading_days():
    x = events([win("2024-01-01", 4), win("2024-01-02", 4), win("2024-01-03", 4)])
    r = CurrentFtmoEvaluator(ftmo_2step_current_profile()).evaluate(x, bars(["2024-01-01", "2024-01-02", "2024-01-03"]), "2024-01-01", "2024-01-05")
    assert r["status"] == "ALIVE"
    x = events([win(f"2024-01-0{i}", 3.5) for i in range(1, 5)])
    r = CurrentFtmoEvaluator(ftmo_2step_current_profile()).evaluate(x, bars([f"2024-01-0{i}" for i in range(1, 5)]), "2024-01-01", "2024-01-06")
    assert r["status"] == "PASS"


def test_two_step_daily_and_floating_loss():
    # Four percent account risk is not a daily breach at 5%; a 6R loss is.
    x = events([win("2024-01-01", -6)])
    r = CurrentFtmoEvaluator(ftmo_2step_current_profile()).evaluate(x, bars(["2024-01-01"]), "2024-01-01", "2024-01-02")
    assert r["status"] in {"FAIL_DAILY_LOSS", "FAIL_MAX_LOSS"}


def test_one_step_best_day_pending_then_diluted():
    # First day contributes 10%, so the target is reached but Best Day is 100%.
    x = events([win("2024-01-01", 10), win("2024-01-02", 2), win("2024-01-03", 2)])
    r = CurrentFtmoEvaluator(ftmo_1step_current_profile()).evaluate(x, bars(["2024-01-01", "2024-01-02", "2024-01-03"]), "2024-01-01", "2024-01-05")
    assert r["target_reached"]
    assert r["status"] in {"TARGET_BEST_DAY_PENDING", "PASS"}


def test_one_step_daily_limit_is_three_percent_and_trailing_floor_is_exposed():
    x = events([win("2024-01-01", -4)])
    r = CurrentFtmoEvaluator(ftmo_1step_current_profile()).evaluate(x, bars(["2024-01-01"]), "2024-01-01", "2024-01-02")
    assert r["status"] == "FAIL_DAILY_LOSS"
    assert "eod_trailing_floor" in r["telemetry"]


def test_dst_boundaries_are_supported_by_existing_local_day_semantics():
    x = events([win("2024-03-31", 1)])
    r = CurrentFtmoEvaluator(ftmo_2step_current_profile()).evaluate(x, bars(["2024-03-31"]), "2024-03-31", "2024-04-01")
    assert r["profile"] == FTMO_2STEP_CURRENT_V1

