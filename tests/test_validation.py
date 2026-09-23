import json
import sqlite3
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import yaml

from sqx_engine.backtest import FastEvaluator
from sqx_engine.config import EngineConfig
from sqx_engine.data.split import TimeSplit, audit_dataset
from sqx_engine.engine import StrategyFactory
from sqx_engine.runtime import CheckpointManager
from sqx_engine.store import StrategyStore
from sqx_engine.strategy import Predicate, StrategyDefinition
from sqx_engine.validation import (ValidationFactory, ValidationStore, check_gates,
                                   degradation, evaluate_stage, final_portfolio)


@pytest.fixture
def frame():
    n = 400
    close = 100 + np.sin(np.arange(n) / 4) + np.arange(n) * .01
    return pd.DataFrame(dict(timestamp=pd.date_range('2020-01-01', periods=n, freq='h', tz='UTC'),
                             open=close, high=close + .5, low=close - .5, close=close, volume=1))


def strategy(always=True):
    return StrategyDefinition('EURUSD', 'H1', 'LONG', (Predicate('close', '>', 0 if always else 999),), stop_atr=10, target_atr=10, time_exit=1)


def known_evaluator():
    frame = pd.DataFrame(dict(timestamp=pd.date_range('2020', periods=6, freq='h', tz='UTC'),
                              open=[100]*6, high=[103]*6, low=[97]*6, close=[100,101,100,99,100,102], volume=1))
    return FastEvaluator(frame, {'close': frame.close.to_numpy(), 'atr_14': np.ones(6)}, 100, .08, .02, engine='numba')


def test_chronological_split_no_overlap(frame):
    s = TimeSplit().partition(frame)
    assert s.development_df.timestamp.max() < s.validation_df.timestamp.min()
    assert s.validation_df.timestamp.max() < s.oos_df.timestamp.min()
    with pytest.raises(ValueError): TimeSplit().partition(frame.iloc[::-1])
    with pytest.raises(ValueError): TimeSplit(.7, .2, .2)


def test_split_uses_all_rows_exactly_once(frame):
    s = TimeSplit().partition(frame.iloc[:397])
    combined = pd.concat([s.development_df, s.validation_df, s.oos_df], ignore_index=True)
    pd.testing.assert_frame_equal(combined, frame.iloc[:397])


def test_validation_does_not_modify_strategy():
    s = strategy(); before = s.to_json(), s.canonical_hash
    evaluate_stage(known_evaluator(), [s], 'VALIDATION', {})
    assert (s.to_json(), s.canonical_hash) == before


@pytest.mark.parametrize('stage', ['VALIDATION', 'OOS'])
def test_validation_metrics_known_answer(stage):
    r = evaluate_stage(known_evaluator(), [strategy()], stage, {'min_trades': 1})[0]['result']
    assert r.trade_count == 3
    assert r.net_profit == pytest.approx(1.7)
    assert r.profit_factor == pytest.approx(2.8 / 1.1)
    assert r.expectancy == pytest.approx(1.7 / 3)
    assert r.expectancy_r == pytest.approx(1.7 / 30)
    assert r.win_rate == pytest.approx(2 / 3)
    rs = np.array([.09, -.11, .19])
    assert r.sharpe == pytest.approx(rs.mean() / rs.std() * np.sqrt(252))
    assert r.max_drawdown == pytest.approx(.011)


def test_oos_metrics_known_answer():
    test_validation_metrics_known_answer('OOS')


def test_gate_reasons_and_invalid_metrics():
    r = known_evaluator().evaluate(strategy())
    bad = replace(r, trade_count=0, profit_factor=.5, expectancy=-1, sharpe=-1)
    assert check_gates(bad, 'VALIDATION', {}) == (False, ['LOW_VALIDATION_TRADES', 'LOW_VALIDATION_PF', 'NEGATIVE_VALIDATION_EXPECTANCY', 'LOW_VALIDATION_SHARPE'])
    assert not check_gates(replace(r, expectancy=float('nan')), 'OOS', {})[0]
    assert check_gates(replace(r, profit_factor=float('inf')), 'OOS', {'min_trades': 1})[0]
    assert degradation(replace(r, profit_factor=0), r)['profit_factor_ratio'] is None


def test_results_store(tmp_path):
    s = strategy(); rows = evaluate_stage(known_evaluator(), [s], 'OOS', {'min_trades': 1})
    path = tmp_path / 'validation.sqlite'
    store = ValidationStore(path)
    store.save('run', 'source', {}, rows, rows, rows); store.close()
    with sqlite3.connect(path) as db:
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        for table in ('development_results', 'validation_results', 'oos_results', 'final_candidates'):
            row = db.execute(f'SELECT source_run_id,canonical_hash,metrics,strategy_json FROM {table}').fetchone()
            assert row[:2] == ('source', s.canonical_hash)
            assert json.loads(row[2])['trade_count'] == 3
            assert row[3] == s.to_json()


def test_empty_survivor_set(frame):
    p = final_portfolio([], frame, 100)
    assert p['selected'] == p['eligible'] == 0
    assert p['status'] == 'FINAL_PORTFOLIO_EMPTY'


def test_partial_portfolio():
    e = known_evaluator(); s = strategy(); r = e.evaluate(s)
    p = final_portfolio([{'result': r, 'development': r}], e.data, 100)
    assert p['selected'] == 1
    assert p['combined_return'] == pytest.approx(.017)
    assert p['combined_max_drawdown'] == pytest.approx(.011)
    assert p['strategy_ids'] == [s.readable_id]


def fixture_source(tmp_path, frame):
    data = tmp_path / 'data.csv'; frame.to_csv(data, index=False)
    source_config = tmp_path / 'source.yaml'
    raw = {'data_path': str(data), 'backtest': {'initial_capital': 100, 'spread': 0., 'slippage': 0.}}
    source_config.write_text(yaml.safe_dump(raw))
    db_path = tmp_path / 'source.sqlite'; store = StrategyStore(db_path)
    store.start_run(('source', None, None, 'EURUSD', 'H1', 'genetic', 1, 2, 2, 2, 2, 0., EngineConfig(raw).config_hash, 'COMPLETE'))
    for s in [strategy(), strategy(False)]:
        store.add_strategy(s, known_evaluator().evaluate(s), {'passed': True, 'stages': {}}, 1, 'CANDIDATE', 'source')
    store.commit(); store.close()
    return EngineConfig({'source_database': str(db_path), 'source_run': 'source', 'source_config': str(source_config),
                         'data_path': str(data), 'data_split': {'development': .7, 'validation': .15, 'oos': .15},
                         'test_type': 'RETROSPECTIVE_SPLIT_TEST', 'validation': {'min_trades': 1, 'min_profit_factor': 0, 'min_expectancy': -999, 'min_sharpe': -999},
                         'oos': {'min_trades': 1, 'min_profit_factor': 0, 'min_expectancy': -999, 'min_sharpe': -999},
                         'results_database': str(tmp_path / 'out.sqlite'), 'summary_path': str(tmp_path / 'summary.json'), 'csv_path': str(tmp_path / 'out.csv')})


def test_oos_only_receives_validation_survivors(tmp_path, frame, monkeypatch):
    import sqx_engine.validation as module
    cfg = fixture_source(tmp_path, frame); seen = {}
    original = module.evaluate_stage
    def spy(evaluator, strategies, stage, gates):
        seen[stage] = [s.canonical_hash for s in strategies]
        return original(evaluator, strategies, stage, gates)
    monkeypatch.setattr(module, 'evaluate_stage', spy)
    before = cfg.resolve_path('source_database').read_bytes()
    summary = ValidationFactory(cfg).run()
    assert seen['OOS'] == [strategy().canonical_hash]
    assert summary['validation']['tested'] == 2 and summary['oos']['tested'] == 1
    assert summary['portfolio']['selected'] == 1
    assert before == cfg.resolve_path('source_database').read_bytes()
    assert len(pd.read_csv(cfg.resolve_path('csv_path'))) == 1


def test_pipeline_empty_survivors(tmp_path, frame, monkeypatch):
    cfg = fixture_source(tmp_path, frame)
    cfg.raw['validation']['min_trades'] = 100000
    result = ValidationFactory(cfg).run()
    assert result['oos']['tested'] == 0
    assert result['portfolio']['status'] == 'FINAL_PORTFOLIO_EMPTY'
    assert pd.read_csv(cfg.resolve_path('csv_path')).empty


def test_source_and_output_safety(tmp_path, frame):
    cfg = fixture_source(tmp_path, frame)
    cfg.raw['test_type'] = 'TRUE_OOS'
    with pytest.raises(ValueError, match='Unverified exposure'): ValidationFactory(cfg).run()
    cfg.raw['results_database'] = cfg.raw['source_database']
    with pytest.raises(ValueError, match='overwrite inputs'): ValidationFactory(cfg).run()


def test_resume_cannot_import_full_data_population(tmp_path):
    p = tmp_path / 'checkpoint.json'; CheckpointManager(p).save({'status': 'COMPLETE'})
    with pytest.raises(ValueError, match='context mismatch'):
        CheckpointManager(p, context={'scope': 'DEVELOPMENT_ONLY'}).load()
    CheckpointManager(p, context={'scope': 'DEVELOPMENT_ONLY'}).save({'status': 'COMPLETE'})
    with pytest.raises(ValueError): CheckpointManager(p).load()


def test_audit_rejects_dirty_data(tmp_path, frame):
    path = tmp_path / 'data.csv'
    pd.concat([frame, frame.iloc[:1]]).to_csv(path, index=False)
    with pytest.raises(ValueError, match='Dataset audit failed'): audit_dataset(path)


def test_no_data_leakage(tmp_path, frame, monkeypatch):
    """Real Genetic ask/evaluate/tell, mutations, crossover, ranking and funnel.

    Alter every later OHLCV value and compare all generated definitions, feedback
    metrics, rejection/ranking and portfolio, not just random initial proposals.
    """
    import sqx_engine.engine as module
    real_prepare = module.prepare_features
    lengths = []
    def guarded_prepare(data):
        lengths.append(len(data)); assert len(data) == 280
        return real_prepare(data)
    monkeypatch.setattr(module, 'prepare_features', guarded_prepare)
    rows, results = [], []
    for i in range(2):
        data = frame.copy()
        if i:
            data.loc[280:, ['open', 'high', 'low', 'close']] *= 1000
            data.loc[280:, 'volume'] = 999999
        data_path = tmp_path / f'data{i}.csv'; data.to_csv(data_path, index=False)
        cfg = EngineConfig({'market': 'EURUSD', 'timeframe': 'H1', 'data_path': str(data_path),
                            'data_split': {'development': .7, 'validation': .15, 'oos': .15},
                            'generator': {'type': 'genetic', 'evaluations': 40, 'seed': 31, 'population_size': 4, 'mode': 'scale'},
                            'engine': 'numba', 'strategy': {'max_predicates': 2},
                            'funnel': {'basic': {'min_trades': 0, 'min_pf': 0., 'min_expectancy': -999, 'min_sharpe': -999},
                                       'stability': {'enabled': False}, 'plateau': {'enabled': True},
                                       'cost_stress': {'enabled': True}, 'execution_stress': {'enabled': True}},
                            'checkpoint': {'path': str(tmp_path / f'checkpoint{i}.json')},
                            'store': {'path': str(tmp_path / f'db{i}.sqlite')}})
        results.append(StrategyFactory(cfg).run())
        with sqlite3.connect(cfg.resolve_path('store.path')) as db:
            rows.append(db.execute('SELECT canonical_hash,strategy_json,trade_count,profit_factor,expectancy,sharpe,quality_score,status,rejection_reason FROM strategies ORDER BY canonical_hash').fetchall())
            provenance = json.loads(db.execute('SELECT manifest FROM discovery_provenance').fetchone()[0])
            assert provenance['scope'] == 'DEVELOPMENT_ONLY'
        checkpoint = json.loads(cfg.resolve_path('checkpoint.path').read_text())
        assert checkpoint['generator']['generation'] > 0
    assert lengths == [280, 280]
    assert len(rows[0]) == 40 and rows[0] == rows[1]
    assert results[0]['portfolio'] == results[1]['portfolio']
    assert results[0]['rejection_reasons'] == results[1]['rejection_reasons']

    # The resulting real clean run is accepted only with matching provenance.
    source_yaml = tmp_path / 'clean.yaml'
    source_yaml.write_text(yaml.safe_dump(cfg.raw))
    validation_cfg = EngineConfig({
        'source_database': str(cfg.resolve_path('store.path')),
        'source_run': results[-1]['run_id'], 'source_config': str(source_yaml),
        'source_checkpoint': str(cfg.resolve_path('checkpoint.path')),
        'data_path': str(data_path), 'data_split': cfg.get('data_split'),
        'results_database': str(tmp_path / 'clean_validation.sqlite'),
        'summary_path': str(tmp_path / 'clean_summary.json'),
        'csv_path': str(tmp_path / 'clean_candidates.csv')})
    clean = ValidationFactory(validation_cfg).run()
    assert clean['data_exposure']['test_type'] == 'TRUE_OOS'
    validation_cfg.raw['data_split'] = {'development': .6, 'validation': .2, 'oos': .2}
    with pytest.raises(ValueError, match='provenance'):
        ValidationFactory(validation_cfg).run()
