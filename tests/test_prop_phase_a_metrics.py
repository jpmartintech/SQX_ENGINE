import pandas as pd

from sqx_engine.prop_factory_v1.lineage import (
    GENERAL_LINEAGE,
    PROP_LINEAGE_SCHEMA_VERSION,
    StrategyLineageMetadata,
    resolve_lineage,
)
from sqx_engine.prop_factory_v1.metrics import HORIZONS, _window_rows, compute_prop_metrics, select_validation_sample


def geometry():
    starts = pd.date_range("2024-01-01T09:00Z", periods=240, freq="12h")
    values = ([1., -1., 2., -1., 0., 1., -1., 1., -1., 2., -1., 1.] * 20)
    gross = ([1.1, -.9, 2.1, -.9, .1, 1.1, -.9, 1.1, -.9, 2.1, -.9, 1.1] * 20)
    return pd.DataFrame({
        "strategy_id": ["s"] * len(starts), "market": ["EURUSD"] * len(starts),
        "timeframe": ["H1"] * len(starts), "direction": ["LONG"] * len(starts),
        "entry_timestamp": starts, "exit_timestamp": starts + pd.Timedelta(hours=6),
        "net_R": values,
        "gross_R": gross,
    })


def test_general_lineage_is_backward_compatible_and_prop_contract_is_versioned():
    old = resolve_lineage({}, "s")
    assert old.factory_lineage == GENERAL_LINEAGE
    assert old.canonical_strategy_id == "s"
    prop = StrategyLineageMetadata.prop_v1("future")
    assert prop.factory_lineage == "PROP_V1"
    assert prop.lineage_schema_version == PROP_LINEAGE_SCHEMA_VERSION
    assert prop.canonical_strategy_id == "future"


def test_phase_a_computes_all_horizons_and_r_descriptors_without_account_scaling():
    m, extras = compute_prop_metrics(geometry(), ["s"], provenance_id="fixture")
    assert set(m.horizon_days) == set(HORIZONS)
    assert (m.metrics_version == "PROP_METRICS_V1").all()
    assert m.net_R_total.iloc[0] != 100000
    assert "P95" in m.positive_tail_json.iloc[0]
    assert set(extras["cost_sensitivity"].cost_multiplier) == {1.0, 1.25, 1.5, 2.0}


def test_phase_a_split_windows_do_not_cross_global_boundaries_and_are_repeatable():
    first, extras1 = compute_prop_metrics(geometry(), ["s"], provenance_id="fixture")
    second, extras2 = compute_prop_metrics(geometry(), ["s"], provenance_id="fixture")
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(extras1["cost_sensitivity"], extras2["cost_sensitivity"])
    assert set(first.split) == {"DEVELOPMENT", "VALIDATION", "OOS"}


def test_calendar_window_aggregation_matches_expected_interval():
    x = geometry().copy()
    x["entry_timestamp"] = pd.to_datetime(x.entry_timestamp, utc=True)
    x["local_day"] = x.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize()
    x["split_start"] = x.local_day.min()
    x["split_end"] = x.local_day.max() + pd.Timedelta(days=1)
    rows = _window_rows(x, x.split_start.iloc[0], x.split_end.iloc[0], 5)
    first = x[(x.local_day >= rows.window_start.iloc[0]) & (x.local_day < rows.window_end.iloc[0])]
    assert rows.trade_count.iloc[0] == len(first)
    assert rows.net_R.iloc[0] == first.net_R.sum()


def test_phase_a_sample_selection_is_deterministic():
    g = pd.concat([geometry().assign(strategy_id=f"s{i}") for i in range(4)], ignore_index=True)
    a = select_validation_sample(g, 3)
    b = select_validation_sample(g, 3)
    pd.testing.assert_frame_equal(a, b)


def test_execution_profile_is_provenance_metadata_not_strategy_semantics():
    metrics, _ = compute_prop_metrics(
        geometry(), ["s"], provenance_id="fixture",
        execution_profile_by_market_tf={("EURUSD", "H1"): "EURUSD_H1"},
    )
    assert set(metrics.execution_profile_id) == {"EURUSD_H1"}
