from dataclasses import replace
from pathlib import Path
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest
import yaml

from sqx_engine.benchmark import fast_regression, manifest
from sqx_engine.config import EngineConfig
from sqx_engine.data.catalog import DataCatalog, resample_closed
from sqx_engine.data.split import audit_dataset, partition_dataset, discovery_manifest
from sqx_engine.grammar import CATALOG
from sqx_engine.library import StrategyLibrary
from sqx_engine.production import ProductionFactory
from sqx_engine.strategy import StrategyDefinition
from sqx_engine.validation import ValidationFactory, DEFAULT_GATES
from test_validation import fixture_source


@pytest.fixture
def bars():
    n=400; c=100 + .005*np.arange(n) + np.sin(np.arange(n)/4)
    return pd.DataFrame(dict(timestamp=pd.date_range('2020-01-01',periods=n,freq='h',tz='UTC'),
                             open=c-.2,high=c+.5,low=c-.5,close=c,volume=np.arange(n)+1))


def put_native(root,frame,market='EURUSD',tf='1H'):
    path=root/'data/cloud'/f'{market}_{tf}.csv'; path.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(path,index=False); return path


def test_catalog_market_timeframe_native_derived_and_missing(tmp_path,bars):
    put_native(tmp_path,bars); catalog=DataCatalog(tmp_path)
    rows=catalog.scan(as_of='2021-01-01')
    assert len(rows)==21
    assert catalog.resolve('EURUSD','H1')['kind']=='native'
    derived=catalog.resolve('EURUSD','H4')
    assert derived['kind']=='derived' and derived['rows']==100
    assert derived['provenance']['source_sha256']==catalog.resolve('EURUSD','H1')['sha256']
    with pytest.raises(FileNotFoundError): catalog.resolve('GBPUSD','H1')
    with pytest.raises(FileNotFoundError): catalog.resolve('EURUSD','M15')
    assert DataCatalog(tmp_path).records==rows


def test_catalog_invalid_dataset_and_sha_provenance(tmp_path,bars):
    path=put_native(tmp_path,bars)
    catalog=DataCatalog(tmp_path); catalog.scan(as_of='2021-01-01')
    bars.loc[0,'volume']=99999; bars.to_csv(path,index=False)
    with pytest.raises(ValueError,match='SHA'): catalog.resolve('EURUSD','H4')
    duplicate=pd.concat([bars,bars.iloc[:1]]); duplicate.to_csv(path,index=False)
    row=next(r for r in catalog.scan() if r['market']=='EURUSD' and r['timeframe']=='H1')
    assert row['status']=='DATASET_INVALID' and row['duplicates']==1


def test_resampling_ohlc_volume_and_complete_bars(bars):
    result=resample_closed(bars.iloc[:10],'H1','H4','2020-01-01 10:00Z')
    assert len(result)==2
    first=result.iloc[0]; expected=bars.iloc[:4]
    assert first.open==expected.open.iloc[0]
    assert first.high==expected.high.max() and first.low==expected.low.min()
    assert first.close==expected.close.iloc[-1] and first.volume==expected.volume.sum()
    assert first.available_at==pd.Timestamp('2020-01-01 04:00Z')
    assert resample_closed(bars.iloc[:3],'H1','H4','2021').empty
    assert len(resample_closed(bars.drop(index=2),'H1','H4','2021'))==99
    with pytest.raises(ValueError): resample_closed(bars,'H1','M15','2021')


def test_causal_resampling_future_mutation_and_partial_bar(bars):
    as_of='2020-01-01 06:30Z'
    before=resample_closed(bars,'H1','H4',as_of)
    future=bars.copy(); future.loc[6:,['open','high','low','close']]*=7
    after=resample_closed(future,'H1','H4',as_of)
    pd.testing.assert_frame_equal(before,after)
    assert len(before)==1 and (before.available_at<=pd.Timestamp(as_of)).all()
    m15=bars.iloc[:32].copy(); m15['timestamp']=pd.date_range('2020',periods=32,freq='15min',tz='UTC')
    h1=resample_closed(m15,'M15','H1','2021')
    h4=resample_closed(h1,'H1','H4','2021')
    direct=resample_closed(m15,'M15','H4','2021')
    pd.testing.assert_frame_equal(h4,direct)


def test_temporal_explicit_ranges_no_overlap_or_future(bars):
    cfg=EngineConfig({'temporal_policy':{'mode':'explicit_dates',
        'development':{'start':'2020-01-01','end':'2020-01-05'},
        'validation':{'start':'2020-01-06','end':'2020-01-10'},
        'oos':{'start':'2020-01-11','end':'latest'}}})
    split=partition_dataset(cfg,bars)
    assert len(split.development_df)==120 and len(split.validation_df)==120 and len(split.oos_df)==160
    assert split.development_df.timestamp.max()<split.validation_df.timestamp.min()<split.oos_df.timestamp.min()
    changed=bars.copy(); changed.loc[120:,['open','high','low','close']]*=4
    pd.testing.assert_frame_equal(split.development_df,partition_dataset(cfg,changed).development_df)
    cfg.raw['temporal_policy']['validation']['start']='2020-01-05'
    with pytest.raises(ValueError,match='overlapping'): partition_dataset(cfg,bars)


def test_market_timeframe_identity_and_determinism():
    s=StrategyDefinition('EURUSD','H1','LONG',(CATALOG['Trend'][0],),grammar_version='v1.7')
    assert len({s.canonical_hash,replace(s,market='GBPUSD').canonical_hash,replace(s,timeframe='M15').canonical_hash})==3
    assert StrategyDefinition.from_json(s.to_json()).canonical_hash==s.canonical_hash


@pytest.fixture
def clean_evidence(tmp_path,bars):
    cfg=fixture_source(tmp_path,bars)
    raw=yaml.safe_load(cfg.resolve_path('source_config').read_text())
    raw.update(market='EURUSD',timeframe='H1',data_split=cfg.raw['data_split'])
    cfg.resolve_path('source_config').write_text(yaml.safe_dump(raw))
    source_cfg=EngineConfig(raw)
    frame,audit=audit_dataset(cfg.resolve_path('data_path'))
    prov=discovery_manifest(source_cfg,audit,partition_dataset(source_cfg,frame))
    with sqlite3.connect(cfg.resolve_path('source_database')) as db:
        db.execute('UPDATE runs SET config_hash=?',(source_cfg.config_hash,))
        db.execute('CREATE TABLE discovery_provenance(run_id TEXT PRIMARY KEY,manifest TEXT NOT NULL)')
        db.execute('INSERT INTO discovery_provenance VALUES (?,?)',('source',json.dumps(prov)))
    cfg.raw['test_type']='TRUE_OOS'; cfg.raw['validation']=DEFAULT_GATES.copy(); cfg.raw['oos']=DEFAULT_GATES.copy()
    result=ValidationFactory(cfg).run()
    assert result['oos']['passed']==1
    return cfg,result


def promote(library,evidence,job='job',level='OOS_PASS'):
    cfg,r=evidence
    return library.promote(cfg.resolve_path('source_database'),cfg.resolve_path('results_database'),r['validation_run_id'],
                           job_id=job,config_path=cfg.resolve_path('source_config'),dataset_path=cfg.resolve_path('data_path'),promotion_level=level)


def test_library_insert_dedup_provenance_filter_stats(tmp_path,clean_evidence):
    library=StrategyLibrary(tmp_path/'library.sqlite')
    try:
        first=promote(library,clean_evidence); assert first['inserted']==1
        second=promote(library,clean_evidence); assert second['inserted']==0 and second['duplicates_rejected']==1 and second['new_observations']==0
        assert library.stats()['total']==1
        row=library.list(market='EURUSD',timeframe='H1')[0]
        assert row['discovery_count']==1 and row['source_run_id']=='source'
        assert json.loads(row['validation_metrics'])['trade_count']>=20
        assert json.loads(row['oos_metrics'])['profit_factor']=='Infinity'
        assert row['dataset_sha256'] and row['job_id']=='job'
        assert library.list(market='GBPUSD')==[]
        assert len(library.list(family=row['family']))==1
        assert library.stats()['by_timeframe']=={'H1':1}
        assert library.db.execute('PRAGMA foreign_key_check').fetchall()==[]
        promote(library,clean_evidence,job='repeat-import')
        assert library.list()[0]['discovery_count']==1
        assert library.db.execute('select count(*) from observations').fetchone()[0]==2
    finally: library.close()


def test_library_lower_levels_are_explicit_analysis(tmp_path,clean_evidence):
    library=StrategyLibrary(tmp_path/'library.sqlite')
    try:
        result=promote(library,clean_evidence,level='GENERATED')
        assert result['inserted']==2 and library.stats()['total']==0
        assert library.stats(include_analysis=True)['total']==2
        promote(library,clean_evidence)
        assert library.stats()['total']==1
    finally: library.close()


def test_library_rejects_orphan_or_changed_provenance(tmp_path,clean_evidence):
    library=StrategyLibrary(tmp_path/'library.sqlite')
    try:
        with pytest.raises(ValueError,match='job_id'): promote(library,clean_evidence,job='')
        cfg,r=clean_evidence
        with sqlite3.connect(cfg.resolve_path('results_database')) as db:
            db.execute('UPDATE validation_results SET passed=0')
        with pytest.raises(ValueError,match='Validation gate'): promote(library,clean_evidence)
        assert library.stats()['total']==0
        assert library.db.execute('select count(*) from library_jobs').fetchone()[0]==0
    finally: library.close()


def setup_batch(root,bars,seeds=(1301,)):
    put_native(root,bars); DataCatalog(root).scan(as_of='2021-01-01')
    raw=yaml.safe_load(Path('configs/eurusd_h1_grammar_v17_smoke.yaml').read_text())
    raw['runtime']['checkpoint_every_evaluations']=5
    path=root/'base.yaml'; path.write_text(yaml.safe_dump(raw))
    return {'base_config':'base.yaml','markets':['EURUSD'],'timeframes':['H1'],'seeds':list(seeds),
            'evaluations_per_job':12,'grammar_version':'v1.7','execution_profiles':{'EURUSD_H1':{'spread':0.,'slippage':0.}}}


def test_job_matrix_expansion_missing_and_costs(tmp_path,bars):
    batch=setup_batch(tmp_path,bars)
    batch.update(markets=['EURUSD','GBPUSD','NZDUSD','USDCAD','USDCHF','USDJPY','XAUUSD'],timeframes=['M15','H1','H4'],seeds=[1301,1302,1303])
    factory=ProductionFactory(tmp_path)
    try:
        jobs=factory.plan(batch); assert len(jobs)==63 and len({j.job_id for j in jobs})==63
        assert sum(j.status=='SKIPPED_DATA_MISSING' for j in jobs)==57
        assert sum(j.status=='FAILED' for j in jobs)==3  # H4 requires explicit costs
        batch['markets']=['GBPUSD']; batch['timeframes']=['H1']; batch['seeds']=[1]
        result=factory.run(batch)
        assert result['counts']=={'SKIPPED_DATA_MISSING':1}
    finally: factory.close()


def test_job_run_resume_complete_and_batch_summary(tmp_path,bars):
    batch=setup_batch(tmp_path,bars); factory=ProductionFactory(tmp_path)
    try:
        first=factory.run(batch)
        assert first['counts']=={'COMPLETE':1},first
        second=factory.run(batch,resume=True)
        assert second==first
        j=first['jobs'][0]; assert j['generated']==12 and j['attempts']==1
        directory=Path(j['directory'])
        for name in ['job.json','dataset.json','discovery.yaml','checkpoint.json','validation.sqlite','promotion.json']:
            assert (directory/name).exists()
        assert list((tmp_path/'runs/production').glob('batch_*.json'))
    finally: factory.close()


def test_interruption_resource_guard_and_resume(tmp_path,bars):
    batch=setup_batch(tmp_path,bars); factory=ProductionFactory(tmp_path)
    try:
        batch['resource_guards']={'max_runtime':.000001}
        first=factory.run(batch)
        assert first['counts']=={'INTERRUPTED':1}
        batch.pop('resource_guards')
        second=factory.run(batch,resume=True)
        assert second['counts']=={'COMPLETE':1},second
        assert second['jobs'][0]['attempts']==2
    finally: factory.close()


def test_failure_isolation_and_deterministic_job_identity(tmp_path,bars,monkeypatch):
    batch=setup_batch(tmp_path,bars,seeds=(1,2)); factory=ProductionFactory(tmp_path)
    original=factory._execute
    def fail_first(job,batch,started):
        if job.seed==1: raise ValueError('test failure')
        return original(job,batch,started)
    monkeypatch.setattr(factory,'_execute',fail_first)
    try:
        assert [j.job_id for j in factory.plan(batch)]==[j.job_id for j in factory.plan(batch)]
        result=factory.run(batch)
        assert result['counts']=={'FAILED':1,'COMPLETE':1}
        assert 'test failure' in next(j['error'] for j in result['jobs'] if j['status']=='FAILED')
    finally: factory.close()


def test_resume_changed_dataset_fails_safely(tmp_path,bars):
    batch=setup_batch(tmp_path,bars); factory=ProductionFactory(tmp_path)
    try:
        batch['resource_guards']={'max_runtime':.000001}; factory.run(batch)
        batch.pop('resource_guards')
        path=tmp_path/'data/cloud/EURUSD_1H.csv'; bars.loc[0,'volume']=999; bars.to_csv(path,index=False)
        result=factory.run(batch,resume=True)
        assert result['counts']=={'FAILED':1}
        assert 'SHA' in result['jobs'][0]['error']
        assert not (Path(result['jobs'][0]['directory'])/'discovery.sqlite').exists()
    finally: factory.close()


def test_v17_fast_regression_and_golden_manifest():
    root=Path(__file__).resolve().parents[1]
    golden=manifest(root)
    assert golden['generated']==250000 and golden['oos_pass']==299
    assert golden['commit']=='e7aae6b279ace1dba47ae395fad5156201acb2f1'
    report=fast_regression(root,check_dataset=False)
    assert report['status']=='PASS',report


def test_native_m15_and_derived_h1_resolution(tmp_path,bars):
    f=bars.copy(); f['timestamp']=pd.date_range('2020',periods=len(f),freq='15min',tz='UTC')
    put_native(tmp_path,f,market='GBPUSD',tf='15M')
    catalog=DataCatalog(tmp_path); catalog.scan(as_of='2021')
    assert catalog.resolve('GBPUSD','M15')['kind']=='native'
    assert catalog.resolve('GBPUSD','H1')['rows']==100
    assert catalog.resolve('GBPUSD','H4')['rows']==25


def test_explicit_temporal_policy_through_production(tmp_path,bars):
    batch=setup_batch(tmp_path,bars)
    batch['temporal_policy']={'mode':'explicit_dates',
        'development':{'start':'2020-01-01','end':'2020-01-05'},
        'validation':{'start':'2020-01-06','end':'2020-01-10'},
        'oos':{'start':'2020-01-11','end':'latest'}}
    factory=ProductionFactory(tmp_path)
    try:
        result=factory.run(batch); assert result['counts']=={'COMPLETE':1},result
        summary=json.loads((Path(result['jobs'][0]['directory'])/'validation_summary.json').read_text())
        assert summary['data_exposure']['test_type']=='TRUE_OOS'
        assert summary['splits']['development']['bars']==120
        assert summary['splits']['validation']['bars']==120
        assert summary['splits']['oos']['bars']==160
    finally: factory.close()


def test_resume_after_validation_does_not_repeat_discovery_or_oos(tmp_path,bars,monkeypatch):
    from sqx_engine.generators import GeneticGenerator
    batch=setup_batch(tmp_path,bars); factory=ProductionFactory(tmp_path)
    original=StrategyLibrary.promote
    def interrupt(*args,**kwargs): raise KeyboardInterrupt()
    monkeypatch.setattr(StrategyLibrary,'promote',interrupt)
    try:
        first=factory.run(batch); assert first['counts']=={'INTERRUPTED':1}
        directory=Path(first['jobs'][0]['directory'])
        def forbidden(*args,**kwargs): raise AssertionError('Completed phase was repeated')
        monkeypatch.setattr(StrategyLibrary,'promote',original)
        monkeypatch.setattr(ValidationFactory,'run',forbidden)
        monkeypatch.setattr(GeneticGenerator,'ask',forbidden)
        (directory/'validation_summary.json').unlink()
        (directory/'final_candidates.csv').unlink()
        second=factory.run(batch,resume=True); assert second['counts']=={'COMPLETE':1},second
        with sqlite3.connect(directory/'validation.sqlite') as db:
            assert db.execute('select count(*) from validation_runs').fetchone()[0]==1
        assert (directory/'validation_summary.json').exists() and (directory/'final_candidates.csv').exists()
    finally: factory.close()


def test_engine_memory_guard_checkpoints_and_resumes(tmp_path,bars):
    from sqx_engine.engine import StrategyFactory
    batch=setup_batch(tmp_path,bars); factory=ProductionFactory(tmp_path)
    try:
        job=factory.plan(batch)[0]; Path(job.directory).mkdir(parents=True)
        config=EngineConfig(job.config)
        stopped=StrategyFactory(config).run(resource_limits={'max_memory_gb':1e-9})
        assert stopped['status']=='INTERRUPTED' and stopped['reason']=='MAX_MEMORY'
        assert config.resolve_path('checkpoint.path').exists()
        complete=StrategyFactory(config).run(resume=True)
        assert complete['unique']==12
        with sqlite3.connect(config.resolve_path('store.path')) as db:
            assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
            assert db.execute('select count(*) from runs').fetchone()[0]==1
    finally: factory.close()


def test_interrupt_funnel_rolls_back_and_resume_matches(tmp_path,bars,monkeypatch):
    import signal
    from sqx_engine.engine import StrategyFactory
    from sqx_engine.funnel import QualityFunnel
    batch=setup_batch(tmp_path,bars); factory=ProductionFactory(tmp_path)
    try: job=factory.plan(batch)[0]
    finally: factory.close()
    raw=job.config.copy()
    raw['funnel']={'basic':{'min_trades':0,'min_pf':0,'min_expectancy':-999,'min_sharpe':-999},
                   'stability':{'enabled':False},'plateau':{'enabled':False},'cost_stress':{'enabled':False},'execution_stress':{'enabled':False}}
    raw['store']={'path':str(tmp_path/'expected.sqlite')}; raw['checkpoint']={'path':str(tmp_path/'expected.json')}
    expected=StrategyFactory(EngineConfig(raw)).run()
    raw['store']={'path':str(tmp_path/'actual.sqlite')}; raw['checkpoint']={'path':str(tmp_path/'actual.json')}
    original=QualityFunnel.evaluate; called=0
    def interrupt(self,*args,**kwargs):
        nonlocal called
        result=original(self,*args,**kwargs); called+=1
        if called==1: signal.raise_signal(signal.SIGINT)
        return result
    monkeypatch.setattr(QualityFunnel,'evaluate',interrupt)
    stopped=StrategyFactory(EngineConfig(raw)).run()
    assert stopped['status']=='INTERRUPTED' and stopped['phase']=='FUNNEL'
    monkeypatch.setattr(QualityFunnel,'evaluate',original)
    actual=StrategyFactory(EngineConfig(raw)).run(resume=True)
    assert actual['counters']==expected['counters']
    assert actual['family_telemetry']==expected['family_telemetry']
    assert actual['portfolio']==expected['portfolio']
    with sqlite3.connect(tmp_path/'expected.sqlite') as left, sqlite3.connect(tmp_path/'actual.sqlite') as right:
        query='select strategy_id,stage,passed,score,reason from funnel order by strategy_id,stage'
        assert left.execute(query).fetchall()==right.execute(query).fetchall()


def test_catalog_rejects_unclosed_native_and_tampered_derivation(tmp_path,bars):
    put_native(tmp_path,bars)
    catalog=DataCatalog(tmp_path); catalog.scan(as_of='2020-01-01 00:30Z')
    with pytest.raises(ValueError,match='unclosed'): catalog.resolve('EURUSD','H1')
    catalog.scan(as_of='2021')
    derived=tmp_path/catalog.resolve('EURUSD','H4')['path']
    f=pd.read_csv(derived); f.loc[0,'volume']+=100; f.to_csv(derived,index=False)
    catalog.scan(as_of='2021')
    with pytest.raises(ValueError,match='provenance'): catalog.resolve('EURUSD','H4')


def test_overlapping_batches_reuse_job_and_keep_membership(tmp_path,bars):
    batch=setup_batch(tmp_path,bars); factory=ProductionFactory(tmp_path)
    try:
        first=factory.run(batch); assert first['counts']=={'COMPLETE':1}
        broader=dict(batch,seeds=[1301,1302])
        second=factory.run(broader)
        assert second['counts']=={'COMPLETE':2}
        assert all(j['attempts']==1 for j in second['jobs'])
        assert factory.status(factory.batch_id(batch))['total']==1
        assert factory.status()['total']==2
    finally: factory.close()


def test_catalog_missing_after_scan_is_missing_not_invalid(tmp_path,bars):
    path=put_native(tmp_path,bars); catalog=DataCatalog(tmp_path); catalog.scan(as_of='2021')
    path.unlink()
    with pytest.raises(FileNotFoundError,match='DATASET_MISSING'): catalog.resolve('EURUSD','H1')


def test_unquoted_yaml_dates_are_serializable(tmp_path,bars):
    path=tmp_path/'dates.yaml'
    path.write_text('''temporal_policy:
  mode: explicit_dates
  development: {start: 2020-01-01, end: 2020-01-05}
  validation: {start: 2020-01-06, end: 2020-01-10}
  oos: {start: 2020-01-11, end: latest}
''')
    cfg=EngineConfig.from_yaml(path)
    assert isinstance(cfg.get('temporal_policy.development.start'),str)
    assert len(cfg.config_hash)==64
    assert len(partition_dataset(cfg,bars).development_df)==120
