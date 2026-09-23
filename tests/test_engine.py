from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sqx_engine.config import EngineConfig
from sqx_engine.engine import StrategyFactory
from sqx_engine.generators import GeneticGenerator
from sqx_engine.strategy import Predicate, StrategyDefinition
from sqx_engine.store import StrategyStore
from sqx_engine.portfolio import PortfolioBuilder
from sqx_engine.backtest import EvaluationResult
from sqx_engine.backtest import FastEvaluator, ParallelEvaluator
from sqx_engine.backtest.numba_core import NUMBA_AVAILABLE
from sqx_engine.runtime import CheckpointManager


def test_strategy_canonical_hash_is_stable():
    a = StrategyDefinition("EURUSD", "H1", "LONG", (Predicate("rsi_14", "<", 40),))
    b = StrategyDefinition("EURUSD", "H1", "LONG", (Predicate("rsi_14", "<", 40),))
    assert a.canonical_hash == b.canonical_hash


def test_store_reopen_and_query(tmp_path: Path):
    path = tmp_path / "store.sqlite"
    store = StrategyStore(path)
    store.start_run(("run", None, None, "EURUSD", "H1", "random", 1, 1, 0, 0, 0, 0.0, "hash", "RUNNING"))
    assert store.count("runs") == 1
    store.close()

    reopened = StrategyStore(path)
    assert reopened.count("runs") == 1
    assert reopened.top_strategies("EURUSD", "H1") == []
    reopened.close()


def test_factory_end_to_end_on_bounded_data(tmp_path: Path):
    n = 180
    close = 1.10 + np.linspace(0, 0.01, n) + 0.001 * np.sin(np.arange(n) / 3)
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"),
        "open": close,
        "high": close + 0.0005,
        "low": close - 0.0005,
        "close": close,
        "volume": 1,
    })
    data_path = tmp_path / "sample.csv"
    frame.to_csv(data_path, index=False)
    config = EngineConfig({
        "market": "EURUSD", "timeframe": "H1", "data_path": str(data_path),
        "generator": {"type": "random", "evaluations": 5, "seed": 7},
        "strategy": {"max_predicates": 1},
        "backtest": {"initial_capital": 10000, "spread": 0.0, "slippage": 0.0},
        "funnel": {"basic": {"min_trades": 0, "min_pf": 0.0, "max_drawdown": 1.0}},
        "portfolio": {"max_strategies": 2, "max_correlation": 0.99},
        "store": {"path": str(tmp_path / "run.sqlite")},
    })
    result = StrategyFactory(config).run()
    assert result["generated"] == 5
    assert result["backtested"] == 5
    assert result["database"]["strategies"] == 5
    assert result["portfolio_selected"] >= 0


def test_genetic_generator_evolves_and_tracks_generations():
    generator = GeneticGenerator("EURUSD", "H1", seed=3, max_predicates=2, population_size=4)
    seen = []
    for _ in range(12):
        strategy = generator.ask()
        seen.append(strategy.canonical_hash)
        class Result:
            expectancy_r = 1.0
            sharpe = 1.0
            max_drawdown = 0.1
        generator.tell(strategy, Result())
    assert len(set(seen)) > 4
    assert generator.generation >= 1
    assert len(generator.elite) <= 4


def test_genetic_state_restores_population_for_resume():
    a = GeneticGenerator("EURUSD", "H1", seed=17, max_predicates=2, population_size=4)
    class Result:
        expectancy_r = 1.0
        sharpe = 1.0
        max_drawdown = 0.1
    for _ in range(12):
        s = a.ask(); a.tell(s, Result())
    state = a.state()
    b = GeneticGenerator("EURUSD", "H1", seed=17, max_predicates=2, population_size=4)
    b.set_state(state)
    assert [(s.canonical_hash, score) for s, score in a.population] == [(s.canonical_hash, score) for s, score in b.population]
    assert a.ask().canonical_hash == b.ask().canonical_hash


def test_scale_mutation_is_effective_and_population_is_bounded():
    generator = GeneticGenerator("EURUSD", "H1", seed=21, max_predicates=2,
                                 population_size=4, mode="scale", novelty_retry_limit=3)
    seen = set()
    class Result:
        expectancy_r = 1.0
        sharpe = 1.0
        max_drawdown = 0.1
    for _ in range(100):
        strategy = generator.ask(known_hashes=seen)
        seen.add(strategy.canonical_hash)
        generator.tell(strategy, Result())
    assert len(generator.population) <= 4
    assert generator.telemetry["mutation_attempts"] > 0
    assert generator.telemetry["mutation_effective"] > 0
    assert generator.telemetry["novelty_retries"] >= 0


def test_scale_generator_is_deterministic():
    def sample():
        g = GeneticGenerator("EURUSD", "H1", seed=31, max_predicates=2,
                             population_size=8, mode="scale")
        seen, values = set(), []
        class Result:
            expectancy_r = 1.0
            sharpe = 1.0
            max_drawdown = 0.1
        for _ in range(60):
            s = g.ask(known_hashes=seen); seen.add(s.canonical_hash); values.append(s.canonical_hash); g.tell(s, Result())
        return values, g.telemetry
    assert sample() == sample()


def test_portfolio_return_normalization_known_answer():
    def result(sid, curve):
        return EvaluationResult(sid, sid, 3, 0, curve[-1] - 1, 1, 0, 0, 0, 0, .5, 0, 1, 1, [0.01, -0.01], curve, [])
    items = [{"result": result("a", [1.0, 1.01, 1.02])}, {"result": result("b", [1.0, .99, 1.00])}]
    portfolio = PortfolioBuilder(2, 1.0).build(items)
    assert np.isclose(portfolio["combined_return"], 0.01)
    assert np.isclose(portfolio["combined_max_drawdown"], 0.0)


def test_checkpoint_save_load_roundtrip(tmp_path: Path):
    manager = CheckpointManager(tmp_path / "checkpoint.json")
    state = {"status": "RUNNING", "evaluations": 4, "rng": {"state": [1, 2, 3]}, "pool": ["a", "b"]}
    manager.save(state)
    assert manager.load() == state


def test_relative_config_path_resolves_from_project_root(tmp_path: Path):
    config_path = tmp_path / "configs" / "x.yaml"
    config_path.parent.mkdir()
    config_path.write_text("data_path: data/cloud/EURUSD_1H.csv\n")
    config = EngineConfig.from_yaml(config_path)
    assert config.resolve_path("data_path") == tmp_path / "data/cloud/EURUSD_1H.csv"


def test_fast_batch_matches_serial(tmp_path: Path):
    n = 100
    close = 1.10 + np.linspace(0, 0.01, n) + 0.001 * np.sin(np.arange(n) / 3)
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"),
        "open": close, "high": close + .0005, "low": close - .0005,
        "close": close, "volume": 1,
    })
    from sqx_engine.features import prepare_features
    from sqx_engine.generators import RandomGenerator
    strategies = [RandomGenerator("EURUSD", "H1", seed=19, max_predicates=1).ask() for _ in range(3)]
    serial = FastEvaluator(frame, prepare_features(frame), cache_size=32)
    expected = serial.evaluate_batch(strategies, rich=False)
    with ParallelEvaluator(frame, prepare_features(frame), 10000, 0.0, 0.0, 2, cache_size=32) as parallel:
        actual = parallel.evaluate_batch(strategies, rich=False)
    assert [(x.canonical_hash, x.trade_count, x.net_profit) for x in actual] == [(x.canonical_hash, x.trade_count, x.net_profit) for x in expected]


@pytest.mark.skipif(not NUMBA_AVAILABLE, reason="Numba optional fallback environment")
def test_numba_matches_python_for_rich_and_stress_paths():
    n = 700
    close = 1.10 + np.linspace(0, 0.02, n) + 0.002 * np.sin(np.arange(n) / 4)
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC"),
        "open": close, "high": close + .0008, "low": close - .0008,
        "close": close, "volume": 1,
    })
    from sqx_engine.features import prepare_features
    generator = __import__("sqx_engine.generators", fromlist=["RandomGenerator"]).RandomGenerator("EURUSD", "H1", seed=9, max_predicates=2)
    py = FastEvaluator(frame, prepare_features(frame), 10000, .00008, .00002, engine="python")
    nb = FastEvaluator(frame, prepare_features(frame), 10000, .00008, .00002, engine="numba")
    fields = ("trade_count", "net_profit", "return_pct", "profit_factor", "expectancy", "expectancy_r", "sharpe", "max_drawdown", "win_rate", "average_trade", "long_trades", "short_trades")
    for _ in range(8):
        strategy = generator.ask()
        for kwargs in ({"rich": False}, {"rich": True}, {"rich": False, "entry_delay": 1}, {"rich": False, "cost_multiplier": 2.0}):
            left, right = py.evaluate(strategy, **kwargs), nb.evaluate(strategy, **kwargs)
            for field in fields:
                assert np.isclose(getattr(left, field), getattr(right, field), rtol=1e-9, atol=1e-10, equal_nan=True)
            if kwargs["rich"]:
                assert left.trades == right.trades
                assert np.allclose(left.equity_curve, right.equity_curve, rtol=1e-9, atol=1e-10)
