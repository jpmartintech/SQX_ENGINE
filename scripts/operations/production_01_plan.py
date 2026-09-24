"""Freeze launch inputs and inspect the 63-job matrix without executing discovery."""
from pathlib import Path
import json, collections, sqlite3
import yaml, pandas as pd
from sqx_engine.config import EngineConfig
from sqx_engine.data.split import audit_dataset, partition_dataset, file_sha256
from sqx_engine.data.catalog import MARKETS
from sqx_engine.production import ProductionFactory, atomic_json
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/production_01'
policy={'name':'PRODUCTION_2016_2026_V1','mode':'explicit_dates','development':{'start':'2016-01-01T00:00:00Z','end':'2022-01-01T00:00:00Z'},'validation':{'start':'2022-01-01T00:00:00Z','end':'2024-01-01T00:00:00Z'},'oos':{'start':'2024-01-01T00:00:00Z','end':'latest'}}
base=yaml.safe_load((ROOT/'configs/eurusd_h1_grammar_v17_250k_clean.yaml').read_text())
base.update(production_policy=policy['name'],production_batch='PRODUCTION_01',temporal_policy=policy)
base.pop('data_split',None)
(ROOT/'configs/production_01_base.yaml').write_text(yaml.safe_dump(base,sort_keys=False))
(ROOT/'configs/production_01_policy.yaml').write_text(yaml.safe_dump({'temporal_policy':policy,'historical_stress_reserved':'timestamp < 2016-01-01T00:00:00Z'},sort_keys=False))
profile={'initial_capital':10000,'spread':0.00008,'slippage':0.00002,'cost_source':'Unchanged EURUSD H1 V1.8 baseline; no separate commission modeled by frozen engine'}
batch={'batch_name':'PRODUCTION_01','production_policy':policy['name'],'base_config':'configs/production_01_base.yaml','markets':list(MARKETS),'timeframes':['M15','H1','H4'],'seeds':[1301,1302,1303],'evaluations_per_job':250000,'grammar_version':'v1.7','workers':1,'execution_profiles':{'EURUSD_H1':profile},'promotion_policy':'OOS_PASS','output_root':'runs/production/PRODUCTION_01','temporal_policy':policy}
(ROOT/'configs/production_01_matrix.yaml').write_text(yaml.safe_dump(batch,sort_keys=False))
f=ProductionFactory(ROOT)
jobs=f.plan(batch); coverage={}; rows=[]
for j in jobs:
    key=(j.market,j.timeframe)
    if key not in coverage and j.dataset.get('path'):
        frame,audit=audit_dataset(ROOT/j.dataset['path']); split=partition_dataset(EngineConfig(j.config),frame)
        parts=split.manifest(); issues=[]
        for stage,start,end in [('development','2016-01-01','2022-01-01'),('validation','2022-01-01','2024-01-01'),('oos','2024-01-01',None)]:
            part=getattr(split,stage+'_df'); expected_start=pd.Timestamp(start,tz='UTC')
            expected_end=pd.Timestamp(end,tz='UTC') if end else frame.timestamp.max()
            weekdays=len(pd.bdate_range(expected_start,expected_end,inclusive='left'))
            expected_slots=weekdays*24*60/{'M15':15,'H1':60,'H4':240}[j.timeframe]
            if part.timestamp.min()>expected_start+pd.Timedelta(days=7) or part.timestamp.max()<expected_end-pd.Timedelta(days=7) or len(part)<.8*expected_slots:
                issues.append(stage+' material coverage shortfall')
        coverage[key]={'splits':parts,'reserved_bars':int((frame.timestamp<pd.Timestamp('2016-01-01',tz='UTC')).sum()),'issues':issues,'rule':'within 7 calendar days of each boundary and >=80% weekday grid slots; weekends/holidays not filled'}
    c=coverage.get(key,{})
    status='READY' if j.status=='PENDING' else {'SKIPPED_DATA_MISSING':'DATASET_MISSING','SKIPPED_DATA_INVALID':'DATASET_INVALID','FAILED':'MISSING_EXECUTION_PROFILE'}.get(j.status,j.status)
    if c.get('issues'): status='INSUFFICIENT_HISTORY'
    rows.append({'job_id':j.job_id,'market':j.market,'timeframe':j.timeframe,'seed':j.seed,'evaluations':j.evaluations,'dataset':j.dataset.get('path'),'dataset_sha256':j.dataset.get('sha256'),'execution_profile':j.config.get('execution_profile'),'status':status,**c})
counts=dict(collections.Counter(r['status'] for r in rows)); ready=[r for r in rows if r['status']=='READY']
plan={'batch':'PRODUCTION_01','batch_id':f.batch_id(batch),'requested':len(rows),'counts':counts,'planned_strategies':len(ready)*250000,'policy':policy,'jobs':rows}
atomic_json(OUT/'plan.json',plan)
lines=['# PRODUCTION_01 — frozen production plan','',f'63 requested; {counts}; {len(ready)*250000} planned strategies.','', '| Market | TF | Seed | Dev | Validation | OOS | Status |','|---|---|---:|---:|---:|---:|---|']
for r in rows:
    s=r.get('splits',{}); lines.append(f"| {r['market']} | {r['timeframe']} | {r['seed']} | {s.get('development',{}).get('bars',0)} | {s.get('validation',{}).get('bars',0)} | {s.get('oos',{}).get('bars',0)} | {r['status']} |")
lines+=['','EURUSD H1 uses the unchanged golden native dataset and V1.8 execution profile. All M15/H4 data are prepared, but smoke-only cost assumptions are not promoted to production profiles. External sqx_lite fee_pips profiles lack an explicit spread/commission decomposition and broker/calibration provenance; they are not silently translated into V1.8 spread.','', 'Pre-2016 bars are HISTORICAL_STRESS_RESERVED. No stress evaluation is performed.']
(OUT/'plan.md').write_text('\n'.join(lines)+'\n')
assert {(r['market'],r['timeframe']) for r in ready}=={('EURUSD','H1')}
readybatch={**batch,'markets':['EURUSD'],'timeframes':['H1']}
(ROOT/'configs/production_01_ready.yaml').write_text(yaml.safe_dump(readybatch,sort_keys=False))
(ROOT/'configs/production_01_canary.yaml').write_text(yaml.safe_dump({**readybatch,'seeds':[1301]},sort_keys=False))
with sqlite3.connect(ROOT/'library/strategies.sqlite') as db:
    snapshot={'total':db.execute('SELECT count(*) FROM strategies').fetchone()[0],'hashes':[r[0] for r in db.execute('SELECT canonical_hash FROM strategies ORDER BY canonical_hash')],'observations':db.execute('SELECT count(*) FROM observations').fetchone()[0]}
if not (OUT/'library_before.json').exists(): atomic_json(OUT/'library_before.json',snapshot)
atomic_json(OUT/'execution_profiles_audit.json',{'accepted':{'EURUSD_H1':profile},'rejected':{'EURUSD_H4':'V1.8 profile explicitly infrastructure smoke, no timeframe calibration','other_market_profiles':'External fee_pips is not an explicit spread/commission profile; no reliable execution provenance'},'external_profile_path':'/home/xaume/proyectos/sqx_lite/market_profiles/profiles.yaml','external_profile_sha256':file_sha256('/home/xaume/proyectos/sqx_lite/market_profiles/profiles.yaml')})
print(json.dumps({k:v for k,v in plan.items() if k!='jobs'},indent=2)); f.close()
