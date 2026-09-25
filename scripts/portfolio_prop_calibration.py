"""RETROSPECTIVE_PROP_RESEARCH over the immutable 6,000 pilot portfolios."""
import csv,json,sqlite3,time,resource
from pathlib import Path
from collections import defaultdict
import numpy as np
from sqx_engine.portfolio_factory.economic import EconomicConfig,AccountEquityEngine
from sqx_engine.portfolio_factory.ftmo import FtmoConfig,FtmoSimulator
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/portfolio_factory_v1/prop_calibration'; OUT.mkdir(parents=True,exist_ok=True)
PILOT=ROOT/'runs/reports/portfolio_factory_v1/pilot_results.csv'; REPLAY=ROOT/'runs/library_replay/replay.sqlite'
RISKS=(.0025,.005,.0075,.01,.0125,.015,.02,.025,.03); HORIZONS=(30,60,90,180,None)
def load_all():
 rows=list(csv.DictReader(PILOT.open(newline=''))); c=sqlite3.connect(REPLAY); allr={}
 for s,t,v in c.execute('select strategy_id,timestamp,net_return from returns'): allr.setdefault(s,[]).append((t,float(v)))
 c.close(); return rows,allr
def portfolio_stream(row,allr):
 ids=json.loads(row['strategy_ids_json']); ws=json.loads(row['weights_json']); vals={}
 for sid in ids:
  for t,v in allr.get(sid,[]): vals[t]=vals.get(t,0.)+float(v)*float(ws[sid])
 ts=np.array(sorted(vals)); return ts,np.array([vals[t] for t in ts],float)
def simulate(raw,ts,risk,horizon,target=.10):
 cfg=FtmoConfig(initial_capital=10000.,profit_target=target,max_daily_loss=.05,max_total_loss=.10,minimum_trading_days=4,max_days=(30 if horizon is not None else None),max_calendar_days=horizon)
 p=AccountEquityEngine(EconomicConfig(initial_capital=10000.,baseline_target=.01,risk_target=risk)).pnl(raw)
 return FtmoSimulator(cfg).run(p,ts)
def target_times(raw,ts,risk):
 cum=np.cumsum(raw*(risk/.01)); out={}
 for target in (.01,.02,.05,.08,.10):
  ix=np.flatnonzero(cum>=target); out[target]=(str(ts[ix[0]]) if len(ix) else '')
 return out
def main():
 started=time.time(); rows,allr=load_all(); groups=defaultdict(list); groupdims=defaultdict(lambda:defaultdict(int)); att=defaultdict(lambda:[0,0]);
 vel_fields=['portfolio_hash','method','size','weighting','risk_target']+[f'time_to_{x}pct' for x in (1,2,5,8,10)]
 chal_fields=['portfolio_hash','method','size','weighting','risk_target','challenge_status','verification_status','both_pass','challenge_days','verification_days','total_days']
 vf=(OUT/'target_velocity.csv').open('w',newline=''); vw=csv.DictWriter(vf,fieldnames=vel_fields);vw.writeheader()
 cf=(OUT/'challenge_verification_results.csv').open('w',newline='');cw=csv.DictWriter(cf,fieldnames=chal_fields);cw.writeheader()
 for row in rows:
  ts,raw=portfolio_stream(row,allr)
  for risk in RISKS:
   tt=target_times(raw,ts,risk); vr={'portfolio_hash':row['portfolio_hash'],'method':row['method'],'size':row['size'],'weighting':row['weighting'],'risk_target':risk,**{f'time_to_{int(k*100)}pct':v for k,v in tt.items()}};vw.writerow(vr)
   for target in (1,2,5,8,10): att[(risk,target)][0]+=1; att[(risk,target)][1]+=bool(vr[f'time_to_{target}pct'])
   for h in HORIZONS:
    x=simulate(raw,ts,risk,h); hk=h if h is not None else 'FULL'; groups[(hk,risk,x['status'])].append((x.get('final_return',x.get('return',0)),x.get('maximum_achieved_return',0),x.get('distance_to_target',0),x.get('max_daily_loss',0),x.get('max_total_drawdown',0)))
   ch=simulate(raw,ts,risk,None,target=.10); ver_status='NOT_RUN'; vd=0; both=0; total=''
   if ch['status']=='PASS':
    ix=np.flatnonzero(np.cumsum(raw*(risk/.01))>=.10)
    if len(ix) and ix[0]+1<len(ts):
     ver=simulate(raw[ix[0]+1:],ts[ix[0]+1:],risk,None,target=.05);ver_status=ver['status'];vd=ver.get('days',0);both=int(ver_status=='PASS');total=ch.get('days',0)+vd
    else:ver_status='DATA_END'
   cw.writerow({'portfolio_hash':row['portfolio_hash'],'method':row['method'],'size':row['size'],'weighting':row['weighting'],'risk_target':risk,'challenge_status':ch['status'],'verification_status':ver_status,'both_pass':both,'challenge_days':ch.get('days',0),'verification_days':vd,'total_days':total})
   groupdims[(row['size'],risk)]['challenge_'+ch['status']]+=1;groupdims[(row['weighting'],risk)]['challenge_'+ch['status']]+=1;groupdims[(row['method'],risk)]['challenge_'+ch['status']]+=1
 vf.close();cf.close()
 def write_rows(path,arr):
  with path.open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(arr[0]) if arr else ['status']);w.writeheader();w.writerows(arr)
 frontier=[];failures=[]
 for h in HORIZONS:
  hk=h if h is not None else 'FULL'
  for risk in RISKS:
   by={st:groups[(hk,risk,st)] for st in ('PASS','FAIL_DAILY','FAIL_TOTAL','TIMEOUT','DATA_END')};n=sum(len(v) for v in by.values());a={'horizon_days':hk,'risk_target':risk,'tested':n}
   for st in by:a[st]=len(by[st]);a[st+'_pct']=len(by[st])/n if n else 0
   frontier.append(a)
   for st,z in by.items():
    if z:failures.append({'status':st,'risk_target':risk,'horizon_days':hk,'count':len(z),'median_final_return':float(np.median([q[0] for q in z])),'median_maximum_achieved_return':float(np.median([q[1] for q in z])),'median_distance_to_target':float(np.median([q[2] for q in z])),'median_max_daily_loss':float(np.median([q[3] for q in z])),'median_max_total_drawdown':float(np.median([q[4] for q in z]))})
 write_rows(OUT/'risk_frontier.csv',frontier);write_rows(OUT/'failure_diagnostics.csv',failures)
 att_rows=[{'risk_target':r,'target_pct':t,'tested':att[(r,t)][0],'reached':att[(r,t)][1],'reached_pct':att[(r,t)][1]/att[(r,t)][0]} for r in RISKS for t in (1,2,5,8,10)];write_rows(OUT/'target_attainment.csv',att_rows)
 for name,field in [('portfolio_size_analysis','size'),('weighting_analysis','weighting'),('search_method_analysis','method')]:
  out=[]
  for value in sorted(set(str(x[field]) for x in rows)):
   for r in RISKS:
    d=groupdims[(value,r)];n=sum(d.values());out.append({field:value,'risk_target':r,'tested':n,**{st:d.get('challenge_'+st,0) for st in ('PASS','FAIL_DAILY','FAIL_TOTAL','TIMEOUT','DATA_END')}})
  write_rows(OUT/f'{name}.csv',out)
 json.dump({'runtime_seconds':time.time()-started,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'portfolios':len(rows),'risk_levels':len(RISKS),'horizons':len(HORIZONS),'simulations':len(rows)*len(RISKS)*len(HORIZONS),'label':'RETROSPECTIVE_PROP_RESEARCH'},open(OUT/'performance.json','w'),indent=2)
 print(json.dumps({'portfolios':len(rows),'simulations':len(rows)*len(RISKS)*len(HORIZONS),'runtime':time.time()-started},indent=2))
if __name__=='__main__':main()
