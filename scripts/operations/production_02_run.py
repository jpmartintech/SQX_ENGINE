"""Operational orchestration only: one frozen V1.8 job per child process."""
from pathlib import Path
from contextlib import closing
from datetime import datetime,timezone
import json,sqlite3,sys,subprocess,time,resource,math,signal
from collections import Counter
from sqx_engine.production import ProductionFactory,atomic_json
from sqx_engine.config import EngineConfig
from sqx_engine.data.split import file_sha256
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/production_02'
MANIFEST=ROOT/'configs/execution_profiles/production_v1.yaml'
def ro(path):
 db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
def verify(j):
 d=Path(j['directory']); assert j['status']=='COMPLETE',j
 cp=json.loads((d/'checkpoint.json').read_text());ds=json.loads((d/'discovery_summary.json').read_text());vs=json.loads((d/'validation_summary.json').read_text())
 assert cp['status']=='COMPLETE' and cp['evaluations']==250000 and j['generated']==250000
 plan=json.loads((OUT/'plan.json').read_text());assert file_sha256(MANIFEST)==plan['manifest_sha256']
 cfg=EngineConfig.from_yaml(d/'discovery.yaml');assert cfg.get('production_batch')=='PRODUCTION_02'
 assert cfg.get('execution_profile_version')=='PRODUCTION_EXECUTION_V1'
 p=next(r for r in plan['jobs'] if r['job_id']==j['job_id'])
 assert cfg.get('backtest.spread')==p['spread'] and cfg.get('backtest.slippage')==p['slippage']
 assert cfg.get('temporal_policy')==plan['production_policy']
 with closing(ro(d/'discovery.sqlite')) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert db.execute('SELECT count(*) FROM strategies').fetchone()[0]==250000
  assert {r[0] for r in db.execute('SELECT canonical_hash FROM strategies')}==set(cp['canonical_hashes'])
  prov=json.loads(db.execute('SELECT manifest FROM discovery_provenance').fetchone()[0]);assert prov['scope']=='DEVELOPMENT_ONLY'
  assert prov['splits']==p['splits']==vs['splits'] and prov['backtest']==cfg.get('backtest')
  assert prov['dataset_sha256']==p['dataset_sha256']
 assert vs['data_exposure']['test_type']=='TRUE_OOS'
 with closing(ro(d/'validation.sqlite')) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert db.execute('SELECT count(*) FROM validation_runs').fetchone()[0]==1
  assert db.execute('SELECT count(*) FROM oos_results WHERE strategy_id NOT IN (SELECT strategy_id FROM validation_results WHERE passed=1)').fetchone()[0]==0
  eligible={r[0] for r in db.execute('SELECT canonical_hash FROM oos_results WHERE passed=1')};assert len(eligible)==j['oos_pass']
  for table in ['development_results','validation_results','oos_results']:
   for r in db.execute(f'SELECT metrics FROM {table}'):
    for key,value in json.loads(r[0]).items():
     if isinstance(value,(float,int)):assert math.isfinite(value) or (key=='profit_factor' and value==float('inf')),(table,key,value)
 with closing(ro(ROOT/'library/strategies.sqlite')) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not db.execute('PRAGMA foreign_key_check').fetchall()
  assert {r[0] for r in db.execute('SELECT canonical_hash FROM observations WHERE job_id=?',(j['job_id'],))}==eligible
  assert set(json.loads((OUT/'library_before.json').read_text())['hashes'])<={r[0] for r in db.execute('SELECT canonical_hash FROM strategies')}
  provenance=json.loads(db.execute('SELECT provenance FROM library_jobs WHERE job_id=?',(j['job_id'],)).fetchone()[0]);assert provenance['config_sha256']==file_sha256(d/'discovery.yaml')
 return {'status':'PASS','job_id':j['job_id'],'metrics':'PASS','execution_costs':'PASS','execution_units':'PASS','development_only':'PASS','validation_oos_isolation':'PASS','db_integrity':'PASS','provenance':'PASS','library_promotion':'PASS','dedup':'PASS','checkpoint':'PASS'}
def child(config):
 subprocess.run(['git','diff','--exit-code','v1.8','--','src','tests','pyproject.toml'],cwd=ROOT,check=True)
 factory=ProductionFactory(ROOT); batch=factory.load_batch(ROOT/config); started=time.perf_counter()
 try:
  plan=json.loads((OUT/'plan.json').read_text());assert file_sha256(MANIFEST)==plan['manifest_sha256']
  frozen_ids={r['job_id'] for r in plan['jobs']}
  prepared=factory.plan(batch);assert len(prepared)==1 and prepared[0].job_id in frozen_ids,'Frozen job input mismatch before execution'
  result=factory.run(batch)
  j=result['jobs'][0];d=Path(j['directory']);resource_path=d/'operational_resources.json';previous=json.loads(resource_path.read_text()) if resource_path.exists() else {}
  atomic_json(resource_path,{'peak_rss_mib':max(previous.get('peak_rss_mib',0),resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024),'wall_seconds':previous.get('wall_seconds',0)+time.perf_counter()-started})
  with factory.db:factory.db.execute('INSERT OR IGNORE INTO batch_jobs VALUES (?,?)',('PRODUCTION_02',j['job_id']))
  if j['status']!='COMPLETE':print(json.dumps({'status':j['status'],'error':j['error']}),flush=True);return 2
  check=verify(j);atomic_json(d/'operational_integrity.json',check);print(json.dumps({'job':j['job_id'],'status':'PASS','oos':j['oos_pass']}),flush=True)
  return 0
 finally:factory.close()
def state():
 with closing(ro(ROOT/'runs/production/jobs.sqlite')) as db:return {r['job_id']:json.loads(r['payload']) for r in db.execute('SELECT job_id,payload FROM jobs')}
def heartbeat(plan,current=None):
 states=state();jobs=[states[r['job_id']] for r in plan['jobs'] if r['job_id'] in states];counts=dict(Counter(j['status'] for j in jobs))
 with closing(ro(ROOT/'library/strategies.sqlite')) as db:total=db.execute('SELECT count(*) FROM strategies').fetchone()[0]
 out={'batch':'PRODUCTION_02','counts':counts,'requested':60,'library':total,'current':None,'utc':datetime.now(timezone.utc).isoformat()}
 if current:
  d=Path(current['directory']);out['current']={k:current[k] for k in ['market','timeframe','seed','canary']};log=d/'production.log'
  lines=log.read_text().splitlines() if log.exists() else [];beats=[s for s in lines if s.startswith('SQX HEARTBEAT')]
  out['heartbeat']=beats[-1] if beats else None
  cp=d/'checkpoint.json'
  if cp.exists():
   c=json.loads(cp.read_text());out['unique_checkpoint']=c['evaluations'];out['phase']='POST_DISCOVERY' if c['evaluations']==250000 else 'GENERATION'
 atomic_json(OUT/'heartbeat.json',out);print(json.dumps(out),flush=True)
 return jobs
def controller():
 plan=json.loads((OUT/'plan.json').read_text());assert file_sha256(MANIFEST)==plan['manifest_sha256']
 ordered=[r for r in plan['jobs'] if r['canary']]+[r for r in plan['jobs'] if not r['canary']]
 blocked=set();failures=[]
 for row in ordered:
  key=(row['market'],row['timeframe'])
  if key in blocked:continue
  existing=state().get(row['job_id']);d=Path(row['directory'])
  if existing and existing['status']=='COMPLETE' and (d/'operational_integrity.json').exists():continue
  if existing and existing['status']=='FAILED':
   failures.append({'job_id':row['job_id'],'error':existing['error']});blocked.add(key);continue
  d.mkdir(parents=True,exist_ok=True)
  with (d/'operation.log').open('a',buffering=1) as log:
   proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'child',row['config']],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
   try:
    while proc.poll() is None:
     heartbeat(plan,row)
     try:proc.wait(timeout=30)
     except subprocess.TimeoutExpired:pass
   except KeyboardInterrupt:
    proc.send_signal(signal.SIGINT);proc.wait();raise
  if proc.returncode:
   j=state().get(row['job_id'],{});error=j.get('error') or (d/'operation.log').read_text()[-3000:]
   failures.append({'job_id':row['job_id'],'error':error});blocked.add(key)
   atomic_json(OUT/'failures.json',failures)
   # Unknown/global integrity failures require a global stop, not silent continuation.
   if j.get('status')!='FAILED' or not any(word in str(error) for word in ['DATASET_', 'Dataset', 'dataset', 'EXECUTION_PROFILE']):raise RuntimeError(f'Global or resource/integrity stop: {error}')
  elif row['canary']:
   atomic_json(OUT/'canaries.json',[{**r,'check':json.loads((Path(r['directory'])/'operational_integrity.json').read_text())} for r in plan['jobs'] if r['canary'] and (Path(r['directory'])/'operational_integrity.json').exists()])
 jobs=heartbeat(plan);atomic_json(OUT/'production_jobs.json',{'jobs':jobs,'counts':dict(Counter(j['status'] for j in jobs)),'failures':failures,'blocked_combinations':[list(x) for x in sorted(blocked)]})
 print('PRODUCTION_02 FINISHED',flush=True)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='child':sys.exit(child(sys.argv[2]))
 controller()
