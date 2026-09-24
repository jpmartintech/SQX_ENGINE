"""Pinned V1.7 golden: fast CI fixture, read-only audit, explicit full replay."""
from contextlib import closing
from pathlib import Path
import copy
import hashlib
import json
import sqlite3

import numpy as np
import pandas as pd
import yaml

from .backtest import FastEvaluator
from .config import EngineConfig
from .data.split import file_sha256
from .features import prepare_features
from .generators import GeneticGenerator
from .library import readonly
from .strategy import StrategyDefinition
from .validation import metrics


def manifest(root):
    value = json.loads((Path(root)/'benchmarks/v1.7/benchmark.json').read_text())
    required = {'commit','dataset_sha256','source_run_id','validation_run_id','grammar_version','split','cost_assumptions',
                'generated','development_candidates','validation_pass','oos_pass','canonical_digest','semantic_files_sha256'}
    if not required <= value.keys(): raise ValueError('Incomplete golden manifest')
    if value['grammar_version'] != 'v1.7' or not len(value['commit']) == 40: raise ValueError('Invalid golden identity')
    return value


def fast_regression(root, check_dataset=True):
    root=Path(root); m=manifest(root); checks={}
    checks['frozen_semantics'] = all(file_sha256(root/p)==h for p,h in m['semantic_files_sha256'].items())
    checks['fixture_sha'] = file_sha256(root/'benchmarks/v1.7/fast_dataset.csv')==m['fast_dataset_sha256'] and file_sha256(root/'benchmarks/v1.7/fast_expected.json')==m['fast_expected_sha256']
    if check_dataset: checks['dataset_sha'] = (root/m['dataset']).exists() and file_sha256(root/m['dataset'])==m['dataset_sha256']
    frame=pd.read_csv(root/'benchmarks/v1.7/fast_dataset.csv'); frame['timestamp']=pd.to_datetime(frame.timestamp,utc=True)
    expected=json.loads((root/'benchmarks/v1.7/fast_expected.json').read_text())
    def replay():
        e=FastEvaluator(frame,prepare_features(frame,grammar_version='v1.7'),**m['cost_assumptions'],engine='numba')
        g=GeneticGenerator(m['market'],m['timeframe'],seed=m['seed'],max_predicates=4,min_predicates=1,grammar_version='v1.7',population_size=40,mode='scale')
        seen=set(); rows=[]
        for _ in expected:
            s=g.ask(seen); r=e.evaluate(s,rich=False); g.tell(s,r); seen.add(s.canonical_hash)
            rows.append((s,metrics(r)))
        return rows
    first,second=replay(),replay()
    checks['strategy_generation']=all(s.to_json()==r['strategy_json'] for (s,_),r in zip(first,expected))
    checks['canonical_hashes']=all(s.canonical_hash==r['canonical_hash'] for (s,_),r in zip(first,expected))
    checks['metrics']=all(np.isclose(float(actual[k]),float(r['metrics'][k]),rtol=1e-10,atol=1e-12,equal_nan=True) for (_,actual),r in zip(first,expected) for k in actual)
    checks['determinism']=all(a.canonical_hash==b.canonical_hash and all(np.isclose(x[k],y[k],rtol=0,atol=0,equal_nan=True) for k in x) for (a,x),(b,y) in zip(first,second))
    return {'mode':'FAST','status':'PASS' if all(checks.values()) else 'FAIL','checks':{k:'PASS' if v else 'FAIL' for k,v in checks.items()},
            'evaluations_per_replay':len(expected),'full_250k_counts':'NOT_RECOMPUTED_IN_FAST'}


def audit_golden(root):
    root=Path(root); m=manifest(root); checks={}
    checks['dataset_sha']=file_sha256(root/m['dataset'])==m['dataset_sha256']
    checks['source_sha']=file_sha256(root/m['source_database'])==m['source_database_sha256']
    checks['validation_sha']=file_sha256(root/m['validation_database'])==m['validation_database_sha256']
    with closing(readonly(root/m['source_database'])) as db:
        checks['integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        run=db.execute('SELECT * FROM runs WHERE run_id=?',(m['source_run_id'],)).fetchone()
        checks['strategy_generation']=run is not None and run['evaluated']==m['generated'] and db.execute('SELECT count(*) FROM strategies').fetchone()[0]==m['generated']
        digest=hashlib.sha256(); hashes_valid=True
        for r in db.execute('SELECT canonical_hash,strategy_json FROM strategies ORDER BY canonical_hash'):
            digest.update((r['canonical_hash']+'\n').encode())
            if StrategyDefinition.from_json(r['strategy_json']).canonical_hash != r['canonical_hash']: hashes_valid=False
        checks['canonical_hashes']=hashes_valid and digest.hexdigest()==m['canonical_digest']
        checks['development_count']=db.execute("SELECT count(*) FROM strategies WHERE status='CANDIDATE'").fetchone()[0]==m['development_candidates']
    checkpoint=json.loads((root/m['checkpoint']).read_text())['result']
    checks['funnel_counts']=all(checkpoint['counters'][key]==m[key] for key in ('basic_pass','stability_pass','plateau_pass','cost_pass','execution_pass'))
    with closing(readonly(root/m['validation_database'])) as db:
        row=db.execute('SELECT summary FROM validation_runs WHERE validation_run_id=?',(m['validation_run_id'],)).fetchone()
        summary=json.loads(row[0]) if row else {}
        checks['validation_counts']=db.execute('SELECT count(*) FROM validation_results WHERE validation_run_id=? AND passed=1',(m['validation_run_id'],)).fetchone()[0]==m['validation_pass']
        checks['oos_counts']=db.execute('SELECT count(*) FROM oos_results WHERE validation_run_id=? AND passed=1',(m['validation_run_id'],)).fetchone()[0]==m['oos_pass']
        checks['final_counts']=db.execute('SELECT count(*) FROM final_candidates WHERE validation_run_id=?',(m['validation_run_id'],)).fetchone()[0]==m['oos_pass'] and summary.get('portfolio',{}).get('after_diversity')==m['final_diversity']
        checks['true_oos']=summary.get('data_exposure',{}).get('test_type')=='TRUE_OOS'
    return {'mode':'AUDIT','status':'PASS' if all(checks.values()) else 'FAIL','checks':{k:'PASS' if v else 'FAIL' for k,v in checks.items()}}


def full_regression(root, output):
    """Explicit expensive 250K run; never called by ordinary pytest or status."""
    from .engine import StrategyFactory
    from .validation import ValidationFactory
    root=Path(root).resolve(); output=Path(output).resolve(); m=manifest(root)
    if output.exists() and any(output.iterdir()): raise ValueError('Full benchmark requires a fresh output directory')
    output.mkdir(parents=True,exist_ok=True)
    cfg=yaml.safe_load((root/'benchmarks/v1.7/discovery.yaml').read_text())
    cfg['data_path']=str(root/m['dataset']); cfg['store']={'path':str(output/'discovery.sqlite')}; cfg['checkpoint']={'path':str(output/'checkpoint.json')}
    cp=output/'discovery.yaml'; cp.write_text(yaml.safe_dump(cfg,sort_keys=False))
    result=StrategyFactory(EngineConfig.from_yaml(cp)).run()
    vc=yaml.safe_load((root/'benchmarks/v1.7/validation.yaml').read_text())
    vc.update(source_run=result['run_id'],source_database=cfg['store']['path'],source_config=str(cp),source_checkpoint=cfg['checkpoint']['path'],
              data_path=cfg['data_path'],results_database=str(output/'validation.sqlite'),summary_path=str(output/'summary.json'),csv_path=str(output/'survivors.csv'))
    summary=ValidationFactory(EngineConfig(vc)).run()
    d=hashlib.sha256()
    with closing(readonly(output/'discovery.sqlite')) as db:
        for h, in db.execute('SELECT canonical_hash FROM strategies ORDER BY canonical_hash'): d.update((h+'\n').encode())
    checks={'canonical_hashes':d.hexdigest()==m['canonical_digest'],
            'funnel_counts':all(result['counters'][k]==m[k] for k in ('basic_pass','stability_pass','plateau_pass','cost_pass','execution_pass')),
            'development_count':result['candidates']==m['development_candidates'],
            'validation_counts':summary['validation']['passed']==m['validation_pass'],
            'oos_counts':summary['oos']['passed']==m['oos_pass'],
            'diversity':summary['portfolio']['after_diversity']==m['final_diversity']}
    report={'mode':'FULL','status':'PASS' if all(checks.values()) else 'FAIL','checks':checks}
    (output/'golden_regression.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
