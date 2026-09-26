import math
from pathlib import Path
import pandas as pd

from sqx_engine.portfolio_factory.universal_economics import StrategyEconomicSpec, apply_profile_cost, geometry_from_atr


def test_long_and_short_geometry_and_target_formula():
    long = geometry_from_atr(1.1000, .002, 2.0, 4.0, "LONG")
    short = geometry_from_atr(1.1000, .002, 2.0, 4.0, "SHORT")
    assert math.isclose(long["stop_price"], 1.096)
    assert math.isclose(long["target_price"], 1.108)
    assert math.isclose(short["stop_price"], 1.104)
    assert math.isclose(short["target_price"], 1.092)
    assert math.isclose(long["target_distance"], .002 * 4.0)


def test_invalid_or_zero_geometry_rejected():
    for args in ((1.1, float("nan"), 2, 4, "LONG"), (1.1, .002, 0, 4, "LONG")):
        try:
            geometry_from_atr(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid geometry accepted")


def test_profile_cost_is_applied_once():
    assert apply_profile_cost(.01, .00008, .00002) == .0099


def test_economic_spec_hash_is_canonical():
    kwargs = dict(strategy_id="s", canonical_hash="h", market="EURUSD", timeframe="H1", direction="LONG", stop_model="ATR", target_model="ATR", time_exit_model="BARS", stop_atr=2., target_atr=4., time_exit_bars=24, execution_profile_id="EURUSD_H1", spread_status="PROFILE_MODEL", spread_model=.00008, commission_status="NOT_APPLICABLE", commission_model="PROFILE_FRICTION", swap_status="UNRESOLVED", swap_model=None, slippage_status="PROFILE_MODEL", slippage_model=.00002)
    a, b = StrategyEconomicSpec(**kwargs), StrategyEconomicSpec(**kwargs)
    assert a.canonical_hash_value() == b.canonical_hash_value()


def test_certified_economic_manifest_full_coverage():
    path = Path("runs/reports/universal_strategy_economics_v1/certified_economic_manifest.parquet")
    if not path.exists():
        return
    manifest = pd.read_parquet(path)
    assert len(manifest) == 8438
    assert manifest.strategy_id.nunique() == 8438
    assert (manifest.geometry_level == "LEVEL_A_GEOMETRY_READY").all()
    assert (manifest.cost_level == "LEVEL_B_PROFILE_COST_READY").all()
    assert manifest.economic_spec_hash.notna().all()


def test_execution_profile_inventory_covers_all_markets_and_timeframes():
    path = Path("runs/reports/universal_strategy_economics_v1/execution_profile_inventory.json")
    if not path.exists():
        return
    profiles = pd.read_json(path)
    assert len(profiles) == 21
    assert set(profiles.execution_profile_id) >= {"EURUSD_H1", "GBPUSD_M15", "XAUUSD_H4"}
