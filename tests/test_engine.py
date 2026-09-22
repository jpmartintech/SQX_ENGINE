from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.config import EngineConfig
from sqx_engine.engine import StrategyFactory
from sqx_engine.generators import GeneticGenerator
from sqx_engine.strategy import Predicate, StrategyDefinition
from sqx_engine.store import StrategyStore
from sqx_engine.portfolio import PortfolioBuilder
from sqx_engine.backtest import EvaluationResult
from sqx_engine.backtest import FastEvaluator, ParallelEvaluator
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
