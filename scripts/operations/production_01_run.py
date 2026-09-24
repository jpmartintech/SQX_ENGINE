"""Operational launch: frozen V1.8 canary, integrity checks, then ready jobs."""
from pathlib import Path
import json, sqlite3, math, time, sys
from collections import Counter
from contextlib import closing
from sqx_engine.production import ProductionFactory, atomic_json
from sqx_engine.config import EngineConfig
from sqx_engine.data.split import file_sha256
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/production_01'

def ro(path): return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
def verify(job):
    assert job['status']=='COMPLETE',job
    d=Path(job['directory']); cp=json.loads((d/'checkpoint.json').read_text()); summary=json.loads((d/'validation_summary.json').read_text())
    assert cp['status']=='COMPLETE' and cp['evaluations']==250000
    assert summary['data_exposure']['test_type']=='TRUE_OOS'
    with closing(ro(d/'discovery.sqlite')) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM strategies').fetchone()[0]==250000
        hashes={r[0] for r in db.execute('SELECT canonical_hash FROM strategies')}; assert hashes==set(cp['canonical_hashes']) and len(hashes)==250000
        prov=json.loads(db.execute('SELECT manifest FROM discovery_provenance').fetchone()[0])
        assert prov['scope']=='DEVELOPMENT_ONLY' and prov['splits']==summary['splits']
        assert prov['temporal_policy']['name']=='PRODUCTION_2016_2026_V1'
        assert prov['splits']['development']['start']>='2016-01-01' and prov['splits']['development']['end']<'2022-01-01'
        assert prov['splits']['validation']['start']>='2022-01-01' and prov['splits']['validation']['end']<'2024-01-01'
        assert prov['splits']['oos']['start']>='2024-01-01'
    infinity_counts=Counter()
    with closing(ro(d/'validation.sqlite')) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM validation_runs').fetchone()[0]==1
        eligible={r[0] for r in db.execute('SELECT canonical_hash FROM oos_results WHERE passed=1')}
        assert len(eligible)==job['oos_pass']
        assert db.execute('SELECT count(*) FROM oos_results WHERE strategy_id NOT IN (SELECT strategy_id FROM validation_results WHERE passed=1)').fetchone()[0]==0
        for table in ['development_results','validation_results','oos_results']:
            for (m,) in db.execute(f'SELECT metrics FROM {table}'):
                for k,v in json.loads(m).items():
                    if isinstance(v,(int,float)):
                        assert not math.isnan(v),(table,k,v)
                        if not math.isfinite(v):
                            assert k=='profit_factor' and v>0,(table,k,v)
                            infinity_counts[table+'.'+k]+=1
    with closing(ro(ROOT/'library/strategies.sqlite')) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('SELECT count(*) FROM strategies').fetchone()[0]==db.execute('SELECT count(DISTINCT canonical_hash) FROM strategies').fetchone()[0]
        promoted={r[0] for r in db.execute('SELECT canonical_hash FROM observations WHERE job_id=?',(job['job_id'],))}
        assert promoted==eligible
        provenance=json.loads(db.execute('SELECT provenance FROM library_jobs WHERE job_id=?',(job['job_id'],)).fetchone()[0])
        assert provenance['config_sha256']==file_sha256(d/'discovery.yaml')
        cfg=EngineConfig.from_yaml(provenance['config_path'])
        assert cfg.get('production_batch')=='PRODUCTION_01' and cfg.get('production_policy')=='PRODUCTION_2016_2026_V1'
        before=json.loads((OUT/'library_before.json').read_text())
        current={r[0] for r in db.execute('SELECT canonical_hash FROM strategies')}; assert set(before['hashes'])<=current
    return {'job_id':job['job_id'],'status':'PASS','db_integrity':'PASS','checkpoint':'PASS','provenance':'PASS','promotion':'PASS','dedup':'PASS','development_isolation':'PASS','validation_isolation':'PASS','true_oos_per_job':'PASS','allowed_infinite_pf':dict(infinity_counts),'promotion_counts':json.loads((d/'promotion.json').read_text())}

if __name__=='__main__':
    factory=ProductionFactory(ROOT)
    try:
        canary=factory.load_batch(ROOT/'configs/production_01_canary.yaml')
        allready=factory.load_batch(ROOT/'configs/production_01_ready.yaml')
        plan=json.loads((OUT/'plan.json').read_text()); expected={r['job_id'] for r in plan['jobs'] if r['status']=='READY'}
        assert {j.job_id for j in factory.plan(allready)}==expected
        atomic_json(OUT/'batch_identity.json',{'name':'PRODUCTION_01','policy':'PRODUCTION_2016_2026_V1','matrix_batch_id':plan['batch_id'],'canary_batch_id':factory.batch_id(canary),'ready_batch_id':factory.batch_id(allready),'job_ids':sorted(expected)})
        print('PRODUCTION_01 CANARY starting/resuming',flush=True)
        result=factory.run(canary)
        atomic_json(OUT/'canary_job.json',result)
        check=verify(result['jobs'][0]); atomic_json(OUT/'canary_check.json',dict(check,status='CANARY_PASS'))
        print('CANARY_PASS',json.dumps(check),flush=True)
        print('PRODUCTION_01 executing all READY jobs; completed canary will be skipped',flush=True)
        result=factory.run(allready)
        atomic_json(OUT/'production_jobs.json',result)
        checks=[]
        for j in result['jobs']:
            if j['status']=='COMPLETE': checks.append(verify(j))
        atomic_json(OUT/'integrity.json',checks)
        with factory.db:
            for j in result['jobs']: factory.db.execute('INSERT OR IGNORE INTO batch_jobs VALUES (?,?)',('PRODUCTION_01',j['job_id']))
        print('PRODUCTION_01',json.dumps(result['counts']),flush=True)
    finally: factory.close()
