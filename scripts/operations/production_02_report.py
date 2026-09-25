"""Descriptive, read-only operational aggregation after frozen production."""
from pathlib import Path
from collections import Counter,defaultdict
from contextlib import closing
import json,sqlite3,csv,subprocess
from sqx_engine.production import atomic_json
from sqx_engine.config import EngineConfig
from sqx_engine.data.split import file_sha256
from sqx_engine.grammar import family_key
from sqx_engine.strategy import StrategyDefinition
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/production_02'
def ro(p):
 d=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True);d.row_factory=sqlite3.Row;return d
def rates(r):
 return {label:r[n]/r[d] if r[d] else None for label,n,d in [('generated_to_dev','development','generated'),('dev_to_val','validation','development'),('val_to_oos','oos','validation'),('dev_to_oos','oos','development'),('generated_to_oos','oos','generated')]}
def main():
 plan=json.loads((OUT/'plan.json').read_text()); assert file_sha256(ROOT/'configs/execution_profiles/production_v1.yaml')==plan['manifest_sha256']
 with closing(ro(ROOT/'runs/production/jobs.sqlite')) as db:states={r['job_id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM jobs')}
 jobs=[];families={k:defaultdict(Counter) for k in ['market','timeframe','market_timeframe']}
 for p in plan['jobs']:
  j=states.get(p['job_id']);
  if not j:continue
  d=Path(j['directory']);r={k:j[k] for k in ['job_id','market','timeframe','seed','status','runtime','attempts','error']}
  if j['status']=='COMPLETE':
   assert json.loads((d/'operational_integrity.json').read_text())['status']=='PASS'
   ds=json.loads((d/'discovery_summary.json').read_text());vs=json.loads((d/'validation_summary.json').read_text());promotion=json.loads((d/'promotion.json').read_text());res=json.loads((d/'operational_resources.json').read_text())
   cfg=EngineConfig.from_yaml(d/'discovery.yaml');assert cfg.get('execution_profile_manifest_sha256')==plan['manifest_sha256'] and cfg.get('temporal_policy')==plan['production_policy']
   r.update(generated=j['generated'],development=j['candidates'],validation=j['validation_pass'],oos=j['oos_pass'],new_unique=promotion['inserted'],rediscovered=promotion['duplicates_rejected'],generation_attempts=ds['attempts'],internal_duplicates=ds['timings']['generator_telemetry'].get('global_duplicate',0),external_duplicates=ds.get('duplicates',0),peak_rss_mib=res['peak_rss_mib'],timings=ds['timings'],source_run_id=ds['run_id'],validation_run_id=vs['validation_run_id'],dataset_sha256=p['dataset_sha256'],execution_profile_version='PRODUCTION_EXECUTION_V1',spread=p['spread'],slippage=p['slippage'],splits=p['splits'])
   fam=Counter();direction=Counter();predicates=Counter()
   with closing(ro(d/'validation.sqlite')) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    for x in db.execute('SELECT strategy_json FROM oos_results WHERE passed=1'):
     s=StrategyDefinition.from_json(x[0]);f=family_key(s);fam[f]+=1;direction[s.direction]+=1;predicates[len(s.predicates)]+=1
     for key,value in [('market',j['market']),('timeframe',j['timeframe']),('market_timeframe',j['market']+' '+j['timeframe'])]:families[key][value][f]+=1
   r.update(oos_family=dict(fam),oos_direction=dict(direction),oos_predicate_count=dict(predicates),survival=rates(r),strategies_per_sec=r['generated']/r['runtime'])
   r['artifacts']={n:{'path':str(d/n),'sha256':file_sha256(d/n)} for n in ['discovery.sqlite','validation.sqlite','checkpoint.json','discovery.yaml','validation.yaml']}
  jobs.append(r)
 aggregates={}
 for dimension in ['market','timeframe','market_timeframe','seed']:
  groups={}
  for r in jobs:
   if r['status']!='COMPLETE':continue
   key=r['market']+' '+r['timeframe'] if dimension=='market_timeframe' else str(r[dimension]);a=groups.setdefault(key,{'generated':0,'development':0,'validation':0,'oos':0,'new_unique':0,'rediscovered':0,'runtime':0,'peak_rss_mib':0,'jobs':0})
   for k in ['generated','development','validation','oos','new_unique','rediscovered','runtime']:a[k]+=r[k]
   a['jobs']+=1;a['peak_rss_mib']=max(a['peak_rss_mib'],r['peak_rss_mib'])
  for a in groups.values():a.update(survival=rates(a),strategies_per_sec=a['generated']/a['runtime'])
  aggregates[dimension]=groups
 before=json.loads((OUT/'library_before.json').read_text());stats={}
 with closing(ro(ROOT/'library/strategies.sqlite')) as db:
  assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not db.execute('PRAGMA foreign_key_check').fetchall()
  hashes={r[0] for r in db.execute('SELECT canonical_hash FROM strategies')};assert set(before['hashes'])<=hashes
  stats['total']=len(hashes);stats['observations']=db.execute('SELECT count(*) FROM observations').fetchone()[0]
  for key in ['market','timeframe','family','direction','predicate_count']:stats['by_'+key]={str(r[0]):r[1] for r in db.execute(f'SELECT {key},count(*) FROM strategies GROUP BY {key}')}
  stats['by_market_timeframe']={r[0]+' '+r[1]:r[2] for r in db.execute('SELECT market,timeframe,count(*) FROM strategies GROUP BY market,timeframe')}
  metadata={}
  for row in db.execute('SELECT * FROM library_jobs'):
   c=EngineConfig.from_yaml(json.loads(row['provenance'])['config_path']);metadata[row['job_id']]={'policy':c.get('production_policy',('V1_8_SMOKE_CHRONOLOGICAL' if row['kind']=='PRODUCTION' else row['kind'])),'execution_profile_version':c.get('execution_profile_version','PRE_PRODUCTION_EXECUTION_V1')}
  for dimension in ['policy','execution_profile_version']:
   stats['by_'+dimension+'_first_discovery']=dict(Counter(metadata[r['job_id']][dimension] for r in db.execute('SELECT job_id FROM strategies')))
  for dimension in ['policy','execution_profile_version']:
   membership=defaultdict(set)
   for r in db.execute('SELECT canonical_hash,job_id FROM observations'):membership[metadata[r['job_id']][dimension]].add(r['canonical_hash'])
   stats['by_'+dimension+'_membership']={key:len(values) for key,values in membership.items()}
  stats['sha256']=file_sha256(ROOT/'library/strategies.sqlite')
 completed=[r for r in jobs if r['status']=='COMPLETE'];sums={k:sum(r[k] for r in completed) for k in ['generated','development','validation','oos','new_unique','rediscovered','runtime']}
 assert before['total']+sums['new_unique']==stats['total']
 protected=json.loads((ROOT/'benchmarks/v1.7/protected_hashes.json').read_text());assert all(file_sha256(ROOT/p)==h for p,h in protected.items())
 subprocess.run(['git','diff','--exit-code','v1.8','--','src','tests','pyproject.toml'],cwd=ROOT,check=True)
 assert subprocess.check_output(['git','rev-parse','v1.8'],cwd=ROOT,text=True).strip()=='16a70ec0db6d58f8adb51ec8ae7caa361e139003'
 assert subprocess.check_output(['git','rev-parse','benchmark-v1.7-eurusd-h1'],cwd=ROOT,text=True).strip()=='e7aae6b279ace1dba47ae395fad5156201acb2f1'
 p01=json.loads((ROOT/'runs/reports/production_01/summary.json').read_text())
 summary={'batch':'PRODUCTION_02','status':'COMPLETE' if len(completed)==60 else 'FAILED','counts':dict(Counter(r['status'] for r in jobs)),'execution_profile_version':'PRODUCTION_EXECUTION_V1','profile_manifest_sha256':plan['manifest_sha256'],'totals':sums,'library_before':before['total'],'library_after':stats['total'],'library':stats,'combined_production_01_02':{'generated':750000+sums['generated'],'oos_observations':652+sums['oos'],'unique_production_policy_members':stats['by_policy_membership'].get('PRODUCTION_2016_2026_V1',0)},'performance':{'summed_job_seconds':sums['runtime'],'strategies_per_sec':sums['generated']/sums['runtime'],'peak_rss_mib':max(r['peak_rss_mib'] for r in completed)},'by':aggregates,'oos_families':{k:{g:dict(v) for g,v in groups.items()} for k,groups in families.items()},'jobs':jobs,'integrity':{'frozen_engine':'PASS','golden_historical_hashes':'PASS','library':'PASS','frozen_execution_profiles':'PASS','policy':'PASS'}}
 atomic_json(OUT/'summary.json',summary);atomic_json(OUT/'library_final.json',stats)
 with (OUT/'market_timeframe.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['market','timeframe','generated','development','validation','oos','new_unique','rediscovered','runtime','peak_rss_mib'])
  for key,a in aggregates['market_timeframe'].items():w.writerow([*key.split(),*[a[k] for k in ['generated','development','validation','oos','new_unique','rediscovered','runtime','peak_rss_mib']]])
 lines=['# PRODUCTION_02 — final operational summary','',summary['status'],'',f"Totals: {sums}",'',f"Library: {before['total']} -> {stats['total']}",'','Complete per-job/group survival, family telemetry, costs, provenance and performance are in summary.json.']
 (OUT/'summary.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':summary['status'],'totals':sums,'library':stats['total']}))
if __name__=='__main__':main()
