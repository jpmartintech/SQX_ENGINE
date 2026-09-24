"""Read-only operational heartbeat; no strategy evaluation or selection."""
from pathlib import Path
import json,re,sqlite3
from datetime import datetime,timezone
from sqx_engine.production import atomic_json
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/production_01'
plan=json.loads((OUT/'plan.json').read_text()); ids={r['job_id'] for r in plan['jobs'] if r['status']=='READY'}
with sqlite3.connect((ROOT/'runs/production/jobs.sqlite').as_uri()+'?mode=ro',uri=True) as db:
 jobs=[json.loads(r[0]) for r in db.execute('SELECT payload FROM jobs')]; jobs=[j for j in jobs if j['job_id'] in ids]
with sqlite3.connect((ROOT/'library/strategies.sqlite').as_uri()+'?mode=ro',uri=True) as db: library=db.execute('SELECT count(*) FROM strategies').fetchone()[0]
complete=[j for j in jobs if j['status']=='COMPLETE']; active=next((j for j in jobs if j['status']=='RUNNING'),None)
value={'batch':'PRODUCTION_01','completed':len(complete),'ready':len(ids),'library_total':library,'current':None,'heartbeat':None}
if active:
 d=Path(active['directory']); value['current']={k:active[k] for k in ['market','timeframe','seed','status','generated','candidates','validation_pass','oos_pass']}
 log=d/'production.log'; lines=log.read_text().splitlines() if log.exists() else []
 beats=[s for s in lines if s.startswith('SQX HEARTBEAT')]
 if beats:value['heartbeat']=beats[-1]
 cp=d/'checkpoint.json'
 if cp.exists():
  state=json.loads(cp.read_text()); value['checkpoint_unique']=state['evaluations']; value['checkpoint_status']=state['status']
  if state['evaluations']==250000 and not active['generated']: value['stage']='FUNNEL_OR_DIVERSITY'
  elif active['generated']: value['stage']='VALIDATION_OOS_OR_PROMOTION'
  else: value['stage']='GENERATION'
 if complete:
  mean=sum(j['runtime'] for j in complete)/len(complete)
  elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(active['started_at'])).total_seconds()
  value['eta_batch_seconds_estimate']=max(0,mean-elapsed)+(len(ids)-len(complete)-1)*mean if elapsed<mean else None
  if elapsed>=mean:value['eta_note']='Current job exceeds observed mean duration; remaining time unknown'
atomic_json(OUT/'heartbeat.json',value); print(json.dumps(value,indent=2))
