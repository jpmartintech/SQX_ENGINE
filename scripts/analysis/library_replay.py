"""AUDIT_ONLY replay of immutable Strategy Library using V1.8 FastEvaluator."""
import argparse,json,sqlite3,time,math,resource,hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np,pandas as pd
from sqx_engine.strategy import StrategyDefinition
from sqx_engine.data.loader import load_ohlcv
from sqx_engine.features import prepare_features
from sqx_engine.backtest import FastEvaluator
ROOT=Path(__file__).resolve().parents[2]; LIB=ROOT/'library/strategies.sqlite'; OUT=ROOT/'runs/library_replay'; OUT.mkdir(parents=True,exist_ok=True); DATA=ROOT/'data/catalog.json'

def safe(x):
 if isinstance(x,(np.integer,)): return int(x)
 if isinstance(x,(np.floating,)): return float(x)
 return x

def profile(m,tf):
 p=json.load(open(ROOT/'runs/reports/production_02/execution_profiles.json'))['profiles'].get(f'{m}_{tf}')
 if p:return p
 # legacy EURUSD H1 uses the frozen baseline profile
 if m=='EURUSD': return {'spread':8e-5,'slippage':2e-5,'initial_capital':10000}
 raise RuntimeError(f'missing execution profile {m}_{tf}')

def dataset(m,tf):
 for d in json.load(open(DATA))['datasets']:
  if d['market']==m and d['timeframe']==tf and d['status'] in ('DATASET_AVAILABLE','DATASET_DERIVED'):
   return ROOT/d['path']
 raise RuntimeError(f'missing dataset {m}_{tf}')

def db_init(path):
 c=sqlite3.connect(path); c.execute('pragma journal_mode=WAL'); c.executescript('''create table if not exists replay_runs(run_id text primary key, version text, created_at text, status text, total integer, complete integer, failed integer, equivalence_status text, metadata text); create table if not exists strategy_replays(strategy_id text primary key, canonical_hash text, market text,timeframe text,direction text,source_policy text,segment text,cost_multiplier real,stored_metrics text,replayed_metrics text,status text,discrepancy text, runtime real); create table if not exists trades(strategy_id text,canonical_hash text,entry_timestamp text,exit_timestamp text,direction text,entry_price real,exit_price real,gross_pnl real,execution_cost real,net_pnl real,net_return real,bars_held integer,reason text); create index if not exists trades_exit on trades(exit_timestamp); create index if not exists trades_strategy on trades(strategy_id); create table if not exists returns(strategy_id text,timestamp text,net_return real); create index if not exists returns_ts on returns(timestamp); create table if not exists cost_results(strategy_id text,cost_multiplier real,metrics text); create table if not exists temporal_results(strategy_id text,segment text,metrics text);'''); c.commit(); return c

def metric_dict(r): return {'trade_count':int(r.trade_count),'profit_factor':float(r.profit_factor),'expectancy':float(r.expectancy),'sharpe':float(r.sharpe),'max_drawdown':float(r.max_drawdown),'net_profit':float(r.net_profit),'return_pct':float(r.return_pct)}
def compare(stored,replayed):
 tolerances={'trade_count':0,'profit_factor':1e-8,'expectancy':1e-10,'sharpe':1e-7,'max_drawdown':1e-10,'net_profit':1e-8,'return_pct':1e-10}; dif={}; ok=True
 for k,t in tolerances.items():
  a=stored.get(k); b=replayed.get(k)
  if a is None: continue
  try: d=abs(float(a)-float(b)) if math.isfinite(float(a)) and math.isfinite(float(b)) else (0 if str(a)==str(b) else float('inf'))
  except: d=float('inf')
  dif[k]=d
  if d>t: ok=False
 return ok,dif

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--sample',type=int); ap.add_argument('--full',action='store_true'); ap.add_argument('--costs',action='store_true'); ap.add_argument('--temporal',action='store_true'); args=ap.parse_args()
 c=sqlite3.connect(LIB); c.row_factory=sqlite3.Row; allrows=list(c.execute('select * from strategies order by canonical_hash')); c.close()
 if args.sample: rows=allrows[:args.sample]
 elif args.full: rows=allrows
 else: rows=allrows[:100]
 run_id=f'audit-{int(time.time())}'; outdb=OUT/'replay.sqlite'; db=db_init(outdb); db.execute('insert or replace into replay_runs values (?,?,?,?,?,?,?,?,?)',(run_id,'AUDIT_ONLY_V1',pd.Timestamp.utcnow().isoformat(),'RUNNING',len(rows),0,0,'PENDING',json.dumps({'sample':bool(args.sample),'full':args.full}))); db.commit()
 groups={}; loaded={}
 for r in rows:
  sj=json.loads(r['strategy_json']); refs=json.loads(r['artifact_references']); key=(r['market'],r['timeframe'],r['oos_start'],r['oos_end'],float(profile(r['market'],r['timeframe'])['spread']),float(profile(r['market'],r['timeframe'])['slippage']))
  if key not in loaded:
   frame=load_ohlcv(dataset(r['market'],r['timeframe'])); start=pd.Timestamp(r['oos_start']); end=pd.Timestamp(r['oos_end']); start=start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC'); end=end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC'); frame=frame[(frame.timestamp>=start)&(frame.timestamp<=end)].reset_index(drop=True); loaded[key]=(frame,prepare_features(frame,grammar_version='v1.7'),profile(r['market'],r['timeframe']))
  groups.setdefault(key,[]).append((r,sj))
 complete=failed=0; equivalence=[]; started=time.time()
 for key,vals in groups.items():
  frame,features,prof=loaded[key]; ev=FastEvaluator(frame,features,prof.get('initial_capital',10000),prof['spread'],prof['slippage'],cache_size=512,engine='numba')
  for r,sj in vals:
   t0=time.perf_counter(); st=StrategyDefinition.from_json(r['strategy_json']); seg='OOS_FULL'; costs=[1.0,1.25,1.5,2.0] if args.costs else [1.0]
   try:
    result=ev.evaluate(st,rich=True,cost_multiplier=1.0); replay=metric_dict(result); stored=json.loads(r['oos_metrics'] or '{}'); ok,dif=compare(stored,replay); status='PASS' if ok else 'DISCREPANCY';
    if args.costs:
     for cm in (1.25,1.5,2.0):
      cr=ev.evaluate(st,rich=False,cost_multiplier=cm); db.execute('insert into cost_results values (?,?,?)',(r['strategy_id'],cm,json.dumps(metric_dict(cr))))
    if args.temporal:
     mid=max(1,len(frame)//2)
     for label,a,b in (('OOS_FIRST_HALF',0,mid),('OOS_SECOND_HALF',mid,len(frame))):
      tr=ev.evaluate(st,start=a,end=b,rich=False,cost_multiplier=1.0); db.execute('insert into temporal_results values (?,?,?)',(r['strategy_id'],label,json.dumps(metric_dict(tr))))
    db.execute('insert or replace into strategy_replays values (?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['strategy_id'],r['canonical_hash'],r['market'],r['timeframe'],r['direction'],r['factory_version'],seg,1.0,json.dumps(stored),json.dumps(replay),status,json.dumps(dif),time.perf_counter()-t0))
    for tr in result.trades:
     ep=float(tr.get('pnl',0))+float(prof['spread'])+float(prof['slippage']); entry_price=None; exit_price=None
     db.execute('insert into trades values (?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['strategy_id'],r['canonical_hash'],str(tr['entry_time']),str(tr['exit_time']),tr['direction'],entry_price,exit_price,ep,float(prof['spread']+prof['slippage']),float(tr['pnl']),float(tr['pnl'])/10000,int(tr['bars_held']),tr['reason']))
     db.execute('insert into returns values (?,?,?)',(r['strategy_id'],str(tr['exit_time']),float(tr['pnl'])/10000))
    if ok: complete+=1
    else: failed+=1
    equivalence.append({'strategy_id':r['strategy_id'],'canonical_hash':r['canonical_hash'],'market':r['market'],'timeframe':r['timeframe'],'stored_trade_count':stored.get('trade_count'),'replayed_trade_count':replay['trade_count'],'stored_pf':stored.get('profit_factor'),'replayed_pf':replay['profit_factor'],'stored_expectancy':stored.get('expectancy'),'replayed_expectancy':replay['expectancy'],'stored_sharpe':stored.get('sharpe'),'replayed_sharpe':replay['sharpe'],'stored_max_drawdown':stored.get('max_drawdown'),'replayed_max_drawdown':replay['max_drawdown'],'status':status,'differences':dif})
   except Exception as e:
    failed+=1; db.execute('insert or replace into strategy_replays values (?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['strategy_id'],r['canonical_hash'],r['market'],r['timeframe'],r['direction'],r['factory_version'],seg,1.0,'{}','{}','FAILED',json.dumps({'error':str(e)}),time.perf_counter()-t0))
  db.commit()
 db.execute('update replay_runs set status=?,complete=?,failed=?,equivalence_status=? where run_id=?',('COMPLETE',complete,failed,'PASS' if failed==0 else 'DISCREPANCY',run_id)); db.commit(); db.close()
 out={'run_id':run_id,'tested':len(rows),'complete':complete,'failed':failed,'equivalence':'PASS' if failed==0 else 'DISCREPANCY','runtime':time.time()-started,'strategies_per_sec':len(rows)/(time.time()-started),'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'database':str(outdb)}
 json.dump(out,open(OUT/'replay_summary.json','w'),indent=2); import csv
 with open(OUT/'replay_equivalence.csv','w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(equivalence[0]) if equivalence else ['strategy_id','status']); w.writeheader(); w.writerows(equivalence)
 print(json.dumps(out,indent=2))
if __name__=='__main__': main()
