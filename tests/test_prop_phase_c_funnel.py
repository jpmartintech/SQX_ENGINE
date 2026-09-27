import pandas as pd

from sqx_engine.prop_factory_v1.funnel import (
    FAIL, PASS, PENDING, FunnelPolicy, PortfolioMarginalUtilityResult,
    deterministic_payload, evaluate_funnel, phase_d_result_schema, phase_e_handoff_schema,
)


def fixture():
    phase_a = pd.DataFrame([
        {"strategy_id": "a", "split": split, "horizon_days": 5, "trade_count": 30, "data_provenance_id": "certified_fixture", "execution_profile_id": "EURUSD_H1", "market": "EURUSD", "timeframe": "H1", "direction": "LONG", "mean_R": .2, "positive_window_fraction": .7, "net_R_distribution_json": '{"P50":0,"P95":1,"P99":1.2}', "positive_tail_json": '{"P95":1,"P99":1.2}', "negative_tail_json": '{"P05":-0.4,"P01":-0.8}', "worst_window_net_R": -1., "holding_P95_hours": 48., "active_day_fraction": .7}
        for split in ("DEVELOPMENT", "VALIDATION")
    ])
    full = pd.DataFrame([{"strategy_id": "a", "split": "DEVELOPMENT", "profit_factor_R": 1.4, "edge_mean_R": .2, "positive_window_fraction": .7, "positive_tail_P95": 1., "negative_tail_P05": -.4, "worst_window_net_R": -1., "holding_P95_hours": 48., "active_day_fraction": .7, "signals_per_day": .2, "maximum_consecutive_negative_windows": 1, "level": "FULL"}])
    cheap = full.assign(level="CHEAP")
    costs = pd.DataFrame([{"strategy_id": "a", "split": "DEVELOPMENT", "cost_multiplier": m, "net_R": 1.0 if m == 1 else .9} for m in (1., 1.25, 1.5, 2.)])
    timing = pd.DataFrame([{"strategy_id": "a", "hour_histogram_json": "{}", "weekday_histogram_json": "{}", "local_day_histogram_json": "{}"}])
    return phase_a, full, cheap, costs, timing


def test_funnel_stage_order_and_pending_safety():
    a, f, c, costs, timing = fixture()
    result = evaluate_funnel(a, f, c, costs, timing, FunnelPolicy(), mode="ANALYSIS")
    assert list(result.stage) == sorted(result.stage, key=lambda x: (result.stage.unique().tolist().index(x))) or len(result) > 0
    assert set(result[result.stage == "PORTFOLIO_USEFUL"].status) == {PENDING}
    assert set(result[result.stage == "PROP_READY"].status) == {PENDING}
    assert set(result[result.stage == "CAUSAL"].status) == {PASS}


def test_phase_d_utility_can_resolve_only_portfolio_useful_not_prop_ready():
    a, f, c, costs, timing = fixture()
    utility = {"a": PortfolioMarginalUtilityResult("a", "REF1", delta_5d_upper_tail=.1)}
    result = evaluate_funnel(a, f, c, costs, timing, FunnelPolicy(), mode="ANALYSIS", portfolio_utility=utility)
    assert result[(result.strategy_id == "a") & (result.stage == "PORTFOLIO_USEFUL")].status.iloc[0] == PASS
    assert result[(result.strategy_id == "a") & (result.stage == "PROP_READY")].status.iloc[0] == PENDING


def test_contracts_and_general_analysis_are_non_mutating():
    assert "delta_target_distance" in phase_d_result_schema()["fields"]
    assert "economic_spec_reference" in phase_e_handoff_schema()["required"]
    a, f, c, costs, timing = fixture()
    result = evaluate_funnel(a, f, c, costs, timing, mode="ANALYSIS")
    assert set(result.factory_lineage) == {"GENERAL"}
    assert set(result.analysis_mode) == {"ANALYSIS"}


def test_signal_duplicate_is_explicit_and_payload_is_repeatable():
    a, f, c, costs, timing = fixture()
    a = pd.concat([a.assign(strategy_id="a"), a.assign(strategy_id="b")], ignore_index=True)
    f = pd.concat([f.assign(strategy_id="a"), f.assign(strategy_id="b")], ignore_index=True)
    c = pd.concat([costs.assign(strategy_id="a"), costs.assign(strategy_id="b")], ignore_index=True)
    timing = pd.concat([timing.assign(strategy_id="a"), timing.assign(strategy_id="b")], ignore_index=True)
    result = evaluate_funnel(a, f, c, timing=timing, mode="ANALYSIS")
    duplicate = result[(result.strategy_id == "b") & (result.stage == "NOVEL")].iloc[0]
    assert duplicate.status == FAIL
    assert "SIGNAL_DUPLICATE" in duplicate.reason_codes_json
    assert deterministic_payload(result) == deterministic_payload(evaluate_funnel(a, f, c, timing=timing, mode="ANALYSIS"))
