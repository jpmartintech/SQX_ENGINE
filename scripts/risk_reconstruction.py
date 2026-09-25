"""Downstream R reconstruction; Strategy Factory remains frozen."""
import csv,json,sqlite3,time,resource,pickle,argparse
from pathlib import Path
from collections import defaultdict
import numpy as np,pandas as pd
from sqx_engine.strategy import StrategyDefinition
from sqx_engine.data.loader import load_ohlcv
from sqx_engine.features import prepare_features
from sqx_engine.backtest import FastEvaluator
from sqx_engine.portfolio_factory.economic import EconomicConfig,AccountEquityEngine
from sqx_engine.portfolio_factory.ftmo import FtmoConfig,FtmoSimulator
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/portfolio_factory_v1/risk_reconstruction'; OUT.mkdir(parents=True,exist_ok=True); LIB=ROOT/'library/strategies.sqlite'; REPLAY=ROOT/'runs/library_replay/replay.sqlite'; CATALOG=ROOT/'data/catalog.json'; PILOT=ROOT/'runs/reports/portfolio_factory_v1/pilot_results.csv'
RISKS=(.0025,.005,.0075,.01,.0125,.015,.02); H=(30,60,90,180,None)
def profile(m,t):
 d=json.load(open(ROOT/'runs/reports/production_02/execution_profiles.json'))['profiles'].get(f'{m}_{t}')
 return d or {'spread':8e-5,'slippage':2e-5,'initial_capital':10000}
def path(m,t):
 for d in json.load(open(CATALOG))['datasets']:
  if d['market']==m and d['timeframe']==t and d['status'] in ('DATASET_AVAILABLE','DATASET_DERIVED'):return ROOT/d['path']
 raise RuntimeError((m,t))
def load_ids():
 rows=list(csv.DictReader(open(PILOT))); ids=[]
 for r in rows:
  for x in json.loads(r['strategy_ids_json']):
   if x not in ids:ids.append(x)
 return rows,ids
def reconstruct(ids):
 c=sqlite3.connect(LIB);c.row_factory=sqlite3.Row; lib={r['strategy_id']:dict(r) for r in c.execute('select * from strategies where strategy_id in (%s)'%(','.join('?'*len(ids))),ids)};c.close(); streams={}; trades=[]; cache={}
 for n,sid in enumerate(ids):
  r=lib[sid]; sj=json.loads(r['strategy_json']); key=(r['market'],r['timeframe'],r['oos_start'],r['oos_end'])
  if key not in cache:
   frame=load_ohlcv(path(r['market'],r['timeframe'])); start=pd.Timestamp(r['oos_start']);end=pd.Timestamp(r['oos_end']);start=start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC');end=end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC');frame=frame[(frame.timestamp>=start)&(frame.timestamp<=end)].reset_index(drop=True);cache[key]=(frame,prepare_features(frame,grammar_version='v1.7'),profile(r['market'],r['timeframe']))
  frame,feat,p=cache[key]; price_map=dict(zip(frame.timestamp.astype(str),frame.open.astype(float))); st=StrategyDefinition.from_json(r['strategy_json']); ev=FastEvaluator(frame,feat,p.get('initial_capital',10000),p['spread'],p['slippage'],cache_size=512,engine='numba'); res=ev.evaluate(st,rich=True)
  sm={}
  for tr in res.trades:
   gross=float(tr['pnl'])+p['spread']+p['slippage']; net=float(tr['pnl']); # evaluator position is exactly one price unit
   # evaluator's r is net pnl / ATR stop distance; derive gross/cost R from it
   net_r=float(tr['r']); risk_price=net/net_r if abs(net_r)>1e-15 else np.nan; gross_r=gross/risk_price if np.isfinite(risk_price) else np.nan; cost_r=(gross-net)/risk_price if np.isfinite(risk_price) else np.nan
   sm[str(tr['exit_time'])]=net_r
   ep=price_map.get(str(tr['entry_time']),np.nan)
   xp=ep+gross if tr['direction']=='LONG' else ep-gross
   sp=ep-risk_price if tr['direction']=='LONG' else ep+risk_price
   trades.append({'strategy_id':sid,'market':r['market'],'timeframe':r['timeframe'],'direction':tr['direction'],'entry_timestamp':str(tr['entry_time']),'exit_timestamp':str(tr['exit_time']),'entry_price':ep,'exit_price':xp,'initial_stop_price':sp,'stop_distance':risk_price,'gross_pnl':gross,'execution_cost':gross-net,'net_pnl':net,'net_return':net/p.get('initial_capital',10000),'evaluator_position_size':1.0,'evaluator_capital':p.get('initial_capital',10000),'gross_R':gross_r,'net_R':net_r,'cost_R':cost_r,'R_status':'DERIVABLE'})
  streams[sid]=sm
 return lib,streams,trades
def simulate(raw,ts,risk,horizon,target=.10):
 if len(ts)==0:return {'status':'DATA_END','days':0,'final_return':0.,'maximum_achieved_return':0.,'distance_to_target':target}
 dates=np.array([str(x)[:10] for x in ts]); start=pd.Timestamp(str(dates[0])); cutoff=(start+pd.Timedelta(days=horizon-1)).strftime('%Y-%m-%d') if horizon is not None else None
 mask=np.array([cutoff is None or d<=cutoff for d in dates]); ds=dates[mask]; rv=np.asarray(raw)[mask]*(risk/.01)
 uniq,inv=np.unique(ds,return_inverse=True); daily=np.zeros(len(uniq));np.add.at(daily,inv,rv)
 cum=np.cumsum(daily); maxret=float(np.max(cum)) if len(cum) else 0.; eqret=cum
 peak=np.maximum.accumulate(np.r_[0.,cum]); dd=np.maximum(peak[1:]-cum,0.)
 daily_breach=np.flatnonzero(daily<-.05); total_breach=np.flatnonzero(cum<-.10); pass_ix=np.flatnonzero((cum>=target)&(np.arange(len(cum))>=3))
 events=[]
 if len(daily_breach):events.append((int(daily_breach[0]),'FAIL_DAILY'))
 if len(total_breach):events.append((int(total_breach[0]),'FAIL_TOTAL'))
 if len(pass_ix):events.append((int(pass_ix[0]),'PASS'))
 if events:
  ix,st=min(events,key=lambda x:x[0]); final=float(cum[ix]);
 else:
  ix=len(cum)-1;final=float(cum[-1]) if len(cum) else 0.;st='TIMEOUT' if horizon is not None and str(dates[-1])[:10]>=cutoff else 'DATA_END'
 return {'status':st,'days':ix+1,'final_return':final,'maximum_achieved_return':maxret,'distance_to_target':target-maxret,'max_daily_loss':float(max(0.,-np.min(daily[:ix+1]))) if len(daily) else 0.,'max_total_drawdown':float(np.max(dd[:ix+1])) if len(dd) else 0.}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,default=0);ap.add_argument('--limit',type=int,default=6000);args=ap.parse_args()
 t0=time.time();rows,ids=load_ids(); rows=rows[args.start:args.start+args.limit];
 cache_stream=OUT/'r_streams.pkl'; suffix=f'_chunk_{args.start}_{args.start+len(rows)}'
 if cache_stream.exists():
  streams=pickle.load(open(cache_stream,'rb')); trades=list(csv.DictReader(open(OUT/'trade_reconstruction.csv'))); lib={}; print('loaded cached reconstruction',len(streams),flush=True)
 else:
  print('reconstructing',len(ids),flush=True);lib,streams,trades=reconstruct(ids);print('reconstructed',len(trades),flush=True);pickle.dump(streams,open(cache_stream,'wb'),protocol=pickle.HIGHEST_PROTOCOL)
 # trade artifact
 with (OUT/'trade_reconstruction.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(trades[0]));w.writeheader();w.writerows(trades)
 # coverage: explicit positive stop parameters are present in all library definitions
 c=sqlite3.connect(LIB);allrows=list(c.execute('select strategy_id,market,timeframe,direction,strategy_json from strategies'));c.close();cov=[]
 for scope,arr in [('LIBRARY',allrows),('CANDIDATE',[(x[0],x[1],x[2],x[3],x[4]) for x in allrows if x[0] in set(sum([json.loads(r['strategy_ids_json']) for r in rows],[]))]),('POOL',[(x[0],x[1],x[2],x[3],x[4]) for x in allrows if x[0] in set(ids)])]:
  d=[json.loads(x[4]).get('stop_atr',0)>0 for x in arr];cov.append({'scope':scope,'total':len(arr),'R_DERIVABLE':sum(d),'R_NOT_DERIVABLE':len(d)-sum(d),'derivable_pct':sum(d)/len(d) if d else 0})
 with (OUT/f'r_coverage{suffix}.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(cov[0]));w.writeheader();w.writerows(cov)
 # market/tf coverage
 by=defaultdict(list)
 for x in allrows:by[(x[1],x[2])].append(x)
 cv=[]
 for (m,t),arr in sorted(by.items()):cv.append({'market':m,'timeframe':t,'total':len(arr),'R_DERIVABLE':sum(json.loads(x[4]).get('stop_atr',0)>0 for x in arr),'R_NOT_DERIVABLE':sum(json.loads(x[4]).get('stop_atr',0)<=0 for x in arr)})
 with (OUT/f'r_coverage_by_market_tf{suffix}.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(cv[0]));w.writeheader();w.writerows(cv)
 # same six-thousand portfolios using R streams
 agg=defaultdict(list);att=defaultdict(lambda:[0,0]);prop=[]
 for row in rows:
  ids0=json.loads(row['strategy_ids_json']);ws=json.loads(row['weights_json']);vals=defaultdict(float)
  for sid in ids0:
   for t,v in streams.get(sid,{}).items():vals[t]+=v*float(ws[sid])
  ts=np.array(sorted(vals));raw=np.array([vals[t] for t in ts])
  for risk in RISKS:
   cum=np.cumsum(raw*(risk/.01)); vel={}
   for q in (1,2,5,8,10):
    ix=np.flatnonzero(cum>=q/100);vel[q]=str(ts[ix[0]]) if len(ix) else '';att[(risk,q)][0]+=1;att[(risk,q)][1]+=bool(vel[q])
   for h in H:
    x=simulate(raw,ts,risk,h);hk=h if h is not None else 'FULL';agg[(hk,risk,x['status'])].append((x.get('final_return',0),x.get('maximum_achieved_return',0),x.get('distance_to_target',0),x.get('max_daily_loss',0),x.get('max_total_drawdown',0)))
 with (OUT/f'r_based_target_attainment{suffix}.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['risk_target','target_pct','tested','reached','reached_pct']);w.writeheader()
  for r in RISKS:
   for q in (1,2,5,8,10):w.writerow({'risk_target':r,'target_pct':q,'tested':att[(r,q)][0],'reached':att[(r,q)][1],'reached_pct':att[(r,q)][1]/att[(r,q)][0]})
 front=[]
 for h in H:
  hk=h if h is not None else 'FULL'
  for r in RISKS:
   d={st:agg[(hk,r,st)] for st in ('PASS','FAIL_DAILY','FAIL_TOTAL','TIMEOUT','DATA_END')};n=sum(map(len,d.values()));row={'horizon_days':hk,'risk_target':r,'tested':n}
   for st in d:row[st]=len(d[st]);row[st+'_pct']=len(d[st])/n if n else 0
   front.append(row)
 with (OUT/f'r_based_risk_frontier{suffix}.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(front[0]));w.writeheader();w.writerows(front)
 # compact prop results
 with (OUT/f'r_based_prop_results{suffix}.csv').open('w',newline='') as f:
  fields=['horizon_days','risk_target','status','count','median_final_return','median_maximum_achieved_return','median_distance_to_target'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for h in H:
   hk=h if h is not None else 'FULL'
   for r in RISKS:
    for st in ('PASS','FAIL_DAILY','FAIL_TOTAL','TIMEOUT','DATA_END'):
     z=agg[(hk,r,st)]
     if z:w.writerow({'horizon_days':hk,'risk_target':r,'status':st,'count':len(z),'median_final_return':float(np.median([x[0] for x in z])),'median_maximum_achieved_return':float(np.median([x[1] for x in z])),'median_distance_to_target':float(np.median([x[2] for x in z]))})
 json.dump({'runtime_seconds':time.time()-t0,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'sample_strategies':len(ids),'trade_rows':len(trades),'portfolios':len(rows),'label':'RETROSPECTIVE_PROP_RESEARCH','R_model':'net_R × account_equity × risk_target','position_size':'frozen evaluator one price unit'},open(OUT/f'performance{suffix}.json','w'),indent=2)
 print(json.dumps({'strategies':len(ids),'trades':len(trades),'runtime':time.time()-t0},indent=2))
if __name__=='__main__':main()
