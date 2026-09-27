from dataclasses import replace

from sqx_engine.prop_factory_v1.generator import (
    PROP_EXIT_SPACE, PROP_GRAMMAR_VERSION, PropGeneticGenerator,
    prop_predicate_catalog,
)
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("prop_generation_pilot_v1", Path(__file__).parents[1] / "scripts/prop_generation_pilot_v1.py")
_pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pilot)
development_validation = _pilot.development_validation


def test_prop_catalog_is_bounded_and_uses_existing_families():
    catalog = prop_predicate_catalog()
    assert set(catalog) == {"Trend", "Momentum", "Volatility", "Structure"}
    assert all(catalog.values())
    assert all("session" not in p.feature for values in catalog.values() for p in values)


def test_prop_generator_lineage_semantics_and_exit_space_are_isolated():
    generator = PropGeneticGenerator("EURUSD", "M15", seed=4101, max_predicates=4, min_predicates=1, mode="scale")
    strategy = generator.ask()
    assert strategy.grammar_version == "v1.7"
    assert strategy.time_exit in PROP_EXIT_SPACE["time_exit_bars"]
    assert strategy.stop_atr in PROP_EXIT_SPACE["stop_atr"]
    assert strategy.target_atr in PROP_EXIT_SPACE["target_atr"]
    assert PROP_GRAMMAR_VERSION == "PROP_GRAMMAR_V1"


def test_prop_generator_determinism():
    def ids():
        generator = PropGeneticGenerator("EURUSD", "H1", seed=4101, max_predicates=4, min_predicates=1, mode="scale")
        return [generator.ask().canonical_hash for _ in range(20)]
    assert ids() == ids()


def test_pilot_split_exposes_only_development_and_validation():
    import pandas as pd
    frame = pd.DataFrame({"value": range(10)})
    development, validation = development_validation(frame)
    assert development.value.tolist() == list(range(7))
    assert validation.value.tolist() == [7]
    assert 9 not in development.value.tolist()
    assert 9 not in validation.value.tolist()
