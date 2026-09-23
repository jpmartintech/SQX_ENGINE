"""V1.7 causality and equivalence. Numeric tolerance: rtol=1e-10, atol=1e-12."""
from dataclasses import replace
import hashlib
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from sqx_engine.backtest import FastEvaluator, ParallelEvaluator
from sqx_engine.backtest.numba_core import NUMBA_AVAILABLE
from sqx_engine.config import EngineConfig
from sqx_engine.engine import StrategyFactory
from sqx_engine.features import prepare_features
from sqx_engine.features.engine import confirmed_structure
from sqx_engine.generators import GeneticGenerator, RandomGenerator
from sqx_engine.grammar import CATALOG, ALL_PREDICATES, FAMILIES, count_stage, family_key, family_totals, search_space
from sqx_engine.strategy import Predicate, StrategyDefinition

RTOL, ATOL = 1e-10, 1e-12


def data(close, width=.3):
    close = np.asarray(close, float)
    return pd.DataFrame(dict(timestamp=pd.date_range('2020', periods=len(close), freq='h', tz='UTC'),
                             open=close, high=close+width, low=close-width, close=close, volume=1))


@pytest.fixture
def wave():
    t = np.arange(700)
    return data(100 + .006*t + np.sin(t/3)*2 + np.sin(t/17)*3)


def definition(predicates, logic='AND', **kwargs):
    return StrategyDefinition('EURUSD', 'H1', 'LONG', tuple(predicates), logic=logic, grammar_version='v1.7', **kwargs)


def bank(frame): return prepare_features(frame, grammar_version='v1.7')


def test_ema_relationship_and_slope():
    frame = data(np.arange(1, 251))
    f = bank(frame)
    ema = frame.close.ewm(span=20, adjust=False, min_periods=20).mean()
    np.testing.assert_allclose(f['trend.close_ema.20'], frame.close-ema, equal_nan=True, rtol=RTOL, atol=ATOL)
    assert np.all(f['trend.ema_pair.10.20'][19:] > 0)
    np.testing.assert_allclose(f['trend.ema_slope.20.3'], ema-ema.shift(3), equal_nan=True, rtol=RTOL, atol=ATOL)
    assert Predicate('trend.ema_slope.20.3', '>', 0).semantic == 'EMA_SLOPE_UP'
    assert Predicate('trend.ema_slope.20.3', '<', 0).semantic == 'EMA_SLOPE_DOWN'


def test_breakout_known_answer():
    frame = data([10]*10 + [12, 8])
    f = bank(frame)
    assert np.isnan(f['trend.breakout_high.10'][:10]).all()
    assert f['trend.breakout_high.10'][10] == pytest.approx(1.7)
    assert f['trend.breakout_low.10'][11] == pytest.approx(-1.7)
    # Current high is 12.3; excluding it is essential for the close=12 breakout.
    assert f['trend.breakout_high.10'][10] > 0


def test_roc_known_answer():
    f = bank(data([10, 11, 12, 13, 15, 22]))
    assert np.isnan(f['momentum.roc.4'][:4]).all()
    np.testing.assert_allclose(f['momentum.roc.4'][4:], [.5, 1.], rtol=RTOL, atol=ATOL)


def test_williams_r_known_answer():
    frame = data(np.arange(10, 40), width=1)
    f = bank(frame)
    # At t=6: highest=17, lowest=9, close=16.
    assert f['momentum.willr.7'][6] == pytest.approx(-12.5)
    flat = bank(data([10]*40, width=0))
    assert np.isnan(flat['momentum.willr.7']).all()


def test_atr_regime_known_answer_and_scale_portability():
    frame = data([100]*100, width=1)
    frame.loc[80:, 'high'] = 103
    frame.loc[80:, 'low'] = 97
    f = bank(frame)
    assert f['volatility.atr_regime.14.50'][79] == pytest.approx(0)
    assert f['volatility.atr_regime.14.50'][80] == pytest.approx((2 + 4/14)/2 - 1)
    scaled = frame.copy(); scaled[['open','high','low','close']] *= 100
    np.testing.assert_allclose(f['volatility.atr_regime.14.50'], bank(scaled)['volatility.atr_regime.14.50'], equal_nan=True, rtol=RTOL, atol=ATOL)


def test_bollinger_known_answer():
    frame = data(np.arange(1, 61))
    f = bank(frame)
    assert f['volatility.bb_middle.20.2'][19] == pytest.approx(9.5)
    assert f['volatility.bb_upper.20.2'][19] == pytest.approx(9.5 - 2*np.std(np.arange(1,21)))
    assert f['volatility.bb_lower.20.2'][19] == pytest.approx(9.5 + 2*np.std(np.arange(1,21)))


def test_keltner_compression_and_expansion():
    compressed = bank(data([100]*80, width=1))
    assert np.isnan(compressed['volatility.compression.20.2.1.5'][:19]).all()
    assert np.all(compressed['volatility.compression.20.2.1.5'][19:] == 1)
    expanded = bank(data(100 + 5*np.sin(np.arange(150)/15), width=.01))
    assert np.any(expanded['volatility.compression.20.2.1.5'][30:] == -1)


@pytest.mark.parametrize('depth', [2,3,5])
def test_fractal_confirmation(depth):
    n = 4*depth+3
    high = np.ones(n)*10; high[depth+1] = 20
    low = np.ones(n)*5
    f = confirmed_structure(high, low, high-1, depth)
    confirmed = 2*depth+1
    assert np.flatnonzero(f['fractal_high'] == 1).tolist() == [confirmed]
    assert np.isnan(f['swing_high'][confirmed])
    assert f['swing_high'][confirmed+1] == 20
    assert not np.any(f['fractal_low'] == 1)  # ties are not strict fractals
    # Changing an as-yet-unseen right-hand bar can remove a future confirmation,
    # but cannot change any published event at the pivot time.
    changed = high.copy(); changed[confirmed] = 30
    altered = confirmed_structure(changed, low, high-1, depth)
    np.testing.assert_equal(f['fractal_high'][:confirmed], altered['fractal_high'][:confirmed])
    assert altered['fractal_high'][confirmed] == 0


def test_hh_hl_lh_ll_known_answer():
    high = np.ones(45)*10; low = np.ones(45)*5
    for i,v in [(3,15),(11,20),(23,18)]: high[i]=v
    for i,v in [(6,2),(17,3),(30,1)]: low[i]=v
    f = confirmed_structure(high, low, np.ones(45)*7, 2)
    assert f['last'][13] == 1  # HH, pivot 11 versus pivot 3
    assert f['last'][19] == 2  # HL, pivot 17 versus pivot 6
    assert f['last'][25] == 3  # LH
    assert f['last'][32] == 4  # LL
    assert np.all(f['last'][32:] == 4)


def test_structure_breakout_known_answer():
    high = np.ones(12)*10; high[3]=15
    low = np.ones(12)*5; close=np.ones(12)*7
    close[5]=7; close[6]=16; high[6]=17
    f = confirmed_structure(high, low, close, 2)
    # Confirmation at 5 cannot be used for a breakout until bar 6.
    assert np.isnan(f['break_high'][5])
    assert f['break_high'][6] == 1
    low[3]=2; close[6]=1; low[6]=.5
    f = confirmed_structure(high, low, close, 2)
    assert np.isnan(f['break_low'][5]) and f['break_low'][6] == -1


def test_dual_fractal_confirmation_is_explicitly_neutral():
    high=np.ones(20)*10; low=np.ones(20)*5
    high[3]=15; low[3]=2; high[10]=20; low[10]=1
    f=confirmed_structure(high,low,np.ones(20)*7,2)
    assert f['last'][12] == 0
    assert f['swing_high'][13] == 20 and f['swing_low'][13] == 1


@pytest.mark.parametrize('logic', ['AND', 'OR'])
def test_canonicalization_predicate_ordering(logic):
    a,b=Predicate('trend.close_ema.20','>',0),Predicate('momentum.roc.8','<',.005)
    x,y=definition([a,b],logic),definition([b,a,a],logic)
    assert x.canonical_hash == y.canonical_hash
    assert x.canonical_json == StrategyDefinition.from_json(x.to_json()).canonical_json
    assert definition([a]).canonical_hash == definition([replace(a,value=0.)],'OR').canonical_hash
    pair1=Predicate('trend.ema_pair.200.20','>',0)
    pair2=Predicate('trend.ema_pair.20.200','<',0.)
    assert definition([pair1]).canonical_hash == definition([pair2]).canonical_hash
    assert definition([Predicate('structure.last.2','==',1)]).canonical_hash != definition([Predicate('structure.last.3','==',1)]).canonical_hash


def test_legacy_json_and_hash_remain_exact():
    raw='{"atr_period":14,"direction":"LONG","logic":"AND","market":"EURUSD","predicates":[{"feature":"rsi_14","operator":"<","value":40}],"stop_atr":1.5,"target_atr":2.0,"time_exit":48,"timeframe":"H1"}'
    s=StrategyDefinition.from_json(raw)
    assert s.to_json()==raw
    assert s.canonical_hash==hashlib.sha256(raw.encode()).hexdigest()
    assert s.grammar_version=='legacy'


@pytest.mark.parametrize('family', FAMILIES)
def test_python_numba_signal_trade_metric_equivalence(wave, family):
    assert NUMBA_AVAILABLE, 'Acceptance requires Numba'
    f=bank(wave)
    py=FastEvaluator(wave,f,10000,.00008,.00002,engine='python',cache_size=256)
    nb=FastEvaluator(wave,f,10000,.00008,.00002,engine='numba',cache_size=256)
    fields=('trade_count','net_profit','profit_factor','expectancy','expectancy_r','sharpe','max_drawdown','win_rate')
    for p in CATALOG[family]:
        s=definition([p])
        assert nb.numeric_predicates(s)==py.numeric_predicates(s)
        np.testing.assert_array_equal(py._signal(s),nb._signal(s))
        for direction in ['LONG','SHORT']:
            s=replace(s,direction=direction)
            a,b=py.evaluate(s),nb.evaluate(s)
            assert a.trades==b.trades
            np.testing.assert_allclose(a.equity_curve,b.equity_curve,rtol=RTOL,atol=ATOL)
            np.testing.assert_allclose([getattr(a,k) for k in fields],[getattr(b,k) for k in fields],rtol=RTOL,atol=ATOL)


@pytest.mark.parametrize('logic', ['AND','OR'])
def test_composition_signal_equivalence(wave, logic):
    f=bank(wave)
    ps=[CATALOG[family][0] for family in FAMILIES]
    s=definition(ps,logic)
    py=FastEvaluator(wave,f,engine='python'); nb=FastEvaluator(wave,f,engine='numba')
    np.testing.assert_array_equal(py._signal(s),nb._signal(s))
    assert py.evaluate(s).trades==nb.evaluate(s).trades


@pytest.mark.parametrize('cut', [13,37,219,419])
def test_future_mutation_changes_no_historical_features_or_signals(wave, cut):
    original=bank(wave)
    modified=wave.copy()
    modified.loc[cut:,['open','high','low','close']]*=17
    changed=bank(modified)
    prefix=bank(wave.iloc[:cut])
    py=FastEvaluator(wave,original,engine='python'); nb=FastEvaluator(modified,changed,engine='numba')
    for key in original:
        np.testing.assert_allclose(original[key][:cut],changed[key][:cut],equal_nan=True,rtol=RTOL,atol=ATOL)
        np.testing.assert_allclose(original[key][:cut],prefix[key],equal_nan=True,rtol=RTOL,atol=ATOL)
    for p in ALL_PREDICATES:
        s=definition([p]); np.testing.assert_array_equal(py._signal(s)[:cut],nb._signal(s)[:cut])


def generator(seed=7, minimum=1):
    return GeneticGenerator('EURUSD','H1',seed=seed,min_predicates=minimum,max_predicates=4,grammar_version='v1.7',population_size=8,mode='scale')


def test_deterministic_scale_checkpoint_resume(wave):
    evaluator=FastEvaluator(wave,bank(wave),engine='numba')
    a,b=generator(),generator()
    seen=set(); families=set()
    for i in range(140):
        x,y=a.ask(seen),b.ask(seen)
        assert x.canonical_json==y.canonical_json
        assert 1<=len(x.predicates)<=4
        assert len(set(x.predicates))==len(x.predicates)
        families.update(family_key(x).split('+')); seen.add(x.canonical_hash)
        result=evaluator.evaluate(x,rich=False); a.tell(x,result); b.tell(y,result)
        if i==65:
            state=json.loads(json.dumps(b.state())); b=generator(); b.set_state(state)
    assert a.state()==b.state()
    assert families==set(FAMILIES)
    assert a.telemetry['mutation_effective']>0 and a.telemetry['crossover_effective']>0
    assert len(a.population)<=8 and a.generation>0
    with pytest.raises(ValueError,match='grammar'):
        GeneticGenerator('EURUSD','H1').set_state(a.state())


def test_composition_bounds_and_family_telemetry():
    gen=generator(minimum=3); counters={}
    for _ in range(100):
        s=gen.ask(); assert 3<=len(s.predicates)<=4
        count_stage(counters,'GENERATED',s)
    totals=family_totals(counters)
    assert totals['single_family']+totals['multi_family']==100
    assert sum(totals['strategies_by_family'].values())==100
    assert totals['multi_family']>0
    audit=search_space(); assert audit['predicate_variants']==len(set(ALL_PREDICATES))==178
    assert audit['syntactic_upper_bound']>100_000_000


def test_parallel_grammar_equivalence(wave):
    f=bank(wave); g=generator(); strategies=[g.ask() for _ in range(6)]
    serial=FastEvaluator(wave,f,engine='numba').evaluate_batch(strategies)
    with ParallelEvaluator(wave,f,10000,0,0,2,engine='numba') as e:
        parallel=e.evaluate_batch(strategies)
    assert [r.trades for r in serial]==[r.trades for r in parallel]


def test_v17_development_isolation_and_factory_resume(tmp_path, wave, monkeypatch):
    import sqx_engine.engine as module
    real=module.prepare_features; lengths=[]
    def guard(frame, **kwargs):
        lengths.append(len(frame)); assert len(frame)==489
        return real(frame, **kwargs)
    monkeypatch.setattr(module,'prepare_features',guard)
    rows=[]; reports=[]
    for i in range(2):
        frame=wave.copy()
        if i: frame.loc[489:,['open','high','low','close']]*=100
        path=tmp_path/f'data{i}.csv'; frame.to_csv(path,index=False)
        cfg=EngineConfig({'market':'EURUSD','timeframe':'H1','data_path':str(path),
                          'data_split':{'method':'chronological','development':.7,'validation':.15,'oos':.15},
                          'strategy':{'grammar_version':'v1.7','min_predicates':1,'max_predicates':4},
                          'generator':{'type':'genetic','mode':'scale','evaluations':60,'population_size':8,'seed':37},
                          'engine':'numba','runtime':{'checkpoint_every_evaluations':10},
                          'store':{'path':str(tmp_path/f'run{i}.sqlite')},'checkpoint':{'path':str(tmp_path/f'checkpoint{i}.json')}})
        r=StrategyFactory(cfg).run(); reports.append(r)
        with sqlite3.connect(cfg.resolve_path('store.path')) as db:
            rows.append(db.execute('select canonical_hash,strategy_json,trade_count,profit_factor,expectancy,sharpe,status from strategies order by canonical_hash').fetchall())
        resumed=StrategyFactory(cfg).run(resume=True)
        assert resumed==r
        assert sum(row.get('GENERATED',0) for row in r['family_telemetry'].values())==60
    assert rows[0]==rows[1] and reports[0]['family_telemetry']==reports[1]['family_telemetry']
    assert lengths==[489,489,489,489]


def test_factory_interrupted_resume_matches_uninterrupted(tmp_path, wave, monkeypatch):
    import signal
    path = tmp_path / 'data.csv'; wave.to_csv(path, index=False)
    raw = {'market': 'EURUSD', 'timeframe': 'H1', 'data_path': str(path),
           'data_split': {'method': 'chronological', 'development': .7, 'validation': .15, 'oos': .15},
           'strategy': {'grammar_version': 'v1.7', 'min_predicates': 1, 'max_predicates': 4},
           'generator': {'type': 'genetic', 'mode': 'scale', 'evaluations': 60, 'population_size': 8, 'seed': 13},
           'engine': 'numba', 'runtime': {'checkpoint_every_evaluations': 10}}
    cfg = EngineConfig({**raw, 'store': {'path': str(tmp_path / 'complete.sqlite')},
                        'checkpoint': {'path': str(tmp_path / 'complete.json')}})
    expected = StrategyFactory(cfg).run()
    interrupted_cfg = EngineConfig({**raw, 'store': {'path': str(tmp_path / 'resume.sqlite')},
                                    'checkpoint': {'path': str(tmp_path / 'resume.json')}})
    original_tell = GeneticGenerator.tell
    count = 0
    def interrupt_at_17(self, strategy, result):
        nonlocal count
        original_tell(self, strategy, result)
        count += 1
        if count == 17: signal.raise_signal(signal.SIGINT)
    monkeypatch.setattr(GeneticGenerator, 'tell', interrupt_at_17)
    stopped = StrategyFactory(interrupted_cfg).run()
    assert stopped['status'] == 'INTERRUPTED' and stopped['unique'] == 17
    monkeypatch.setattr(GeneticGenerator, 'tell', original_tell)
    actual = StrategyFactory(interrupted_cfg).run(resume=True)
    for key in ['counters', 'family_telemetry', 'portfolio', 'rejection_reasons']:
        assert actual[key] == expected[key]
    def rows(config):
        with sqlite3.connect(config.resolve_path('store.path')) as db:
            return db.execute('select canonical_hash,strategy_json,trade_count,profit_factor,expectancy,status from strategies order by canonical_hash').fetchall()
    assert rows(cfg) == rows(interrupted_cfg)
