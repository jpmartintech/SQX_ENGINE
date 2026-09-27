import json

import pandas as pd

from sqx_engine.prop_factory_v1.fitness import (
    CHEAP_OBJECTIVES,
    dominates,
    evaluate_cheap,
    evaluate_full,
    fitness_vector,
    normalize_objectives,
    pareto_rank,
)


def rows():
    tail = json.dumps({"P01": -1.0, "P05": -0.5, "P10": -0.25, "P75": 0.5, "P90": 0.8, "P95": 1.0, "P99": 1.2})
    return pd.DataFrame([
        {"strategy_id": "a", "split": "DEVELOPMENT", "horizon_days": 5, "metrics_version": "PROP_METRICS_V1", "data_provenance_id": "fixture", "execution_profile_id": "EURUSD_H1", "mean_R": .2, "median_R": .1, "positive_window_fraction": .6, "signals_per_day": 1., "active_day_fraction": .8, "worst_window_net_R": -1., "maximum_consecutive_negative_windows": 2, "holding_P50_hours": 12., "holding_P95_hours": 60., "positive_tail_json": tail, "negative_tail_json": tail},
        {"strategy_id": "b", "split": "DEVELOPMENT", "horizon_days": 5, "metrics_version": "PROP_METRICS_V1", "data_provenance_id": "fixture", "execution_profile_id": "EURUSD_H1", "mean_R": .2, "median_R": .1, "positive_window_fraction": .6, "signals_per_day": 2., "active_day_fraction": .8, "worst_window_net_R": -1., "maximum_consecutive_negative_windows": 2, "holding_P50_hours": 12., "holding_P95_hours": 60., "positive_tail_json": tail, "negative_tail_json": tail},
    ])


def test_cheap_and_full_are_deterministic_and_preserve_missing_pf():
    frame = rows()
    cheap = evaluate_cheap(frame)
    full = evaluate_full(frame)
    assert cheap.equals(evaluate_cheap(frame))
    assert full.equals(evaluate_full(frame))
    assert set(cheap.level) == {"CHEAP"}
    assert set(full.level) == {"FULL"}
    assert full.profit_factor_R.isna().all()
    assert set(full.profit_factor_R__status) == {"UNAVAILABLE"}
    assert "positive_tail_json" in full.columns
    assert "negative_tail_json" in full.columns


def test_pareto_direction_and_frequency_without_edge():
    frame = evaluate_cheap(rows())
    ranked = pareto_rank(frame, CHEAP_OBJECTIVES)
    assert ranked.loc[ranked.strategy_id == "b", "pareto_front"].iloc[0] == 0
    assert dominates(frame.iloc[1], frame.iloc[0], CHEAP_OBJECTIVES)
    assert not dominates(frame.iloc[0], frame.iloc[1], CHEAP_OBJECTIVES)


def test_normalization_and_vector_serialization():
    full = evaluate_full(rows())
    normalized = normalize_objectives(full)
    assert normalized.edge_mean_R__normalized.between(0, 1).all()
    vector = fitness_vector(full, "a").to_dict()
    assert vector["strategy_id"] == "a"
    assert vector["objectives"]["profit_factor_R"]["status"] == "UNAVAILABLE"


def test_cost_sensitivity_and_split_isolation():
    frame = rows()
    costs = pd.DataFrame([
        {"strategy_id": "a", "split": "DEVELOPMENT", "cost_multiplier": 1.0, "net_R": 2.0},
        {"strategy_id": "a", "split": "DEVELOPMENT", "cost_multiplier": 2.0, "net_R": 1.0},
    ])
    full = evaluate_full(frame, costs)
    assert full.loc[full.strategy_id == "a", "cost_degradation_2x_R"].iloc[0] == -1.0
    assert evaluate_full(frame.assign(split="VALIDATION")).empty


def test_optional_certified_ledger_profit_factor_is_explicit():
    full = evaluate_full(rows(), profit_factor_by_strategy_split={("a", "DEVELOPMENT"): 2.5})
    value = full.loc[full.strategy_id == "a", "profit_factor_R"].iloc[0]
    assert value == 2.5
    assert full.loc[full.strategy_id == "a", "profit_factor_R__status"].iloc[0] == "AVAILABLE"


def test_direct_rolling_tail_fields_override_trade_tail_fallback():
    frame = rows()
    frame["positive_tail_P95"] = [4.0, 5.0]
    frame["positive_tail_P99"] = [6.0, 7.0]
    frame["negative_tail_P01"] = [-4.0, -5.0]
    frame["negative_tail_P05"] = [-2.0, -3.0]
    result = evaluate_cheap(frame)
    assert result.loc[result.strategy_id == "a", "positive_tail_P95"].iloc[0] == 4.0
    assert result.loc[result.strategy_id == "a", "negative_tail_P05"].iloc[0] == -2.0
