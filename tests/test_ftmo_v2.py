import pandas as pd

from sqx_engine.portfolio_factory.ftmo_v2 import (
    Ftmo2StepProfile,
    Ftmo2StepSimulator,
    _local_day,
    canonical_portfolio_hash,
    normalize_weights,
)


def events(rows):
    return pd.DataFrame(rows, columns=["entry_time", "exit_time", "net_return"])


def test_ftmo_profile_and_static_limits():
    p = Ftmo2StepProfile()
    assert p.name == "FTMO_2STEP_V1"
    assert p.initial_capital == 1.0
    assert p.challenge_target == .10
    assert p.verification_target == .05
    assert p.daily_loss_fraction == .05
    assert p.maximum_loss_limit == .90
    assert p.minimum_trading_days == 4


def test_cest_day_boundaries_are_not_utc_boundaries():
    assert _local_day("2024-01-01T22:30:00Z", "Europe/Paris") == "2024-01-01"
    assert _local_day("2024-01-01T23:30:00Z", "Europe/Paris") == "2024-01-02"
    assert _local_day("2024-03-31T21:30:00Z", "Europe/Paris") == "2024-03-31"
    assert _local_day("2024-03-31T22:30:00Z", "Europe/Paris") == "2024-04-01"


def test_challenge_requires_target_and_four_open_days():
    rows = [(f"2024-01-{d:02d}T10:00Z", f"2024-01-{d:02d}T11:00Z", 3.0) for d in (1, 2, 3, 4)]
    result = Ftmo2StepSimulator().run(events(rows), target=.10, risk_fraction=.01)
    assert result["status"] == "PASS"
    assert result["trading_days"] == 4


def test_target_is_not_pass_while_position_remains_open():
    rows = [
        ("2024-01-01T10:00Z", "2024-01-02T11:00Z", 12.0),
        ("2024-01-01T10:01Z", "2024-01-05T11:00Z", 1.0),
    ]
    result = Ftmo2StepSimulator().run(events(rows), target=.10, risk_fraction=.01)
    assert result["status"] == "RIGHT_CENSORED"


def test_daily_and_maximum_loss_are_distinct_rules():
    daily = Ftmo2StepSimulator().run(events([
        ("2024-01-01T10:00Z", "2024-01-01T11:00Z", -0.06),
    ]), risk_fraction=.01)
    assert daily["status"] == "DAILY_LOSS_FAIL"
    maximum = Ftmo2StepSimulator().run(events([
        ("2024-01-01T10:00Z", "2024-01-01T11:00Z", -0.03),
        ("2024-01-02T10:00Z", "2024-01-02T11:00Z", -0.08),
    ]), risk_fraction=.01)
    assert maximum["status"] == "MAX_LOSS_FAIL"


def test_right_censoring_is_not_failure():
    result = Ftmo2StepSimulator().run(events([
        ("2024-01-01T10:00Z", "2024-01-01T11:00Z", .1),
    ]), target=.10, risk_fraction=.01)
    assert result["status"] == "RIGHT_CENSORED"


def test_weights_are_bounded_and_hash_is_order_invariant():
    w = normalize_weights(["b", "a", "c", "d", "e"], max_single_fraction=.20)
    assert abs(sum(w.values()) - 1.0) < 1e-12
    assert max(w.values()) <= .20 + 1e-12
    h1 = canonical_portfolio_hash(["a", "b"], {"a": .5, "b": .5}, "PORTFOLIO_TOTAL_RISK", .01, .02, "EQUAL_RISK")
    h2 = canonical_portfolio_hash(["b", "a"], {"b": .5, "a": .5}, "PORTFOLIO_TOTAL_RISK", .01, .02, "EQUAL_RISK")
    assert h1 == h2


def test_normalized_path_is_account_size_independent():
    # FTMO V2 operates in initial-capital-normalized units; the same event
    # path is intentionally independent of nominal account denomination.
    p = Ftmo2StepProfile()
    assert p.initial_capital == 1.0
    assert p.to_dict()["daily_loss_amount"] == .05
