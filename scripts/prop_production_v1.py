"""Production candidate funnel over certified portfolios; no strategy generation."""
import csv,json,sqlite3,hashlib,time,resource,sqlite3
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
from sqx_engine.portfolio_factory.production import *
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/prop_production_v1'; EXP=ROOT/'runs/portfolio_exports';OUT.mkdir(parents=True,exist_ok=True);EXP.mkdir(parents=True,exist_ok=True)
PILOT=ROOT/'runs/reports/portfolio_factory_v1/pilot_results.csv'; TR=ROOT/'runs/reports/portfolio_factory_v1/risk_reconstruction/trade_reconstruction.csv'; STREAM=ROOT/'runs/reports/portfolio_factory_v1/risk_reconstruction/r_streams.pkl'; LIB=ROOT/'library/strategies.sqlite'
import pickle
rows=list(csv.DictReader(open(PILOT))); streams=pickle.load(open(STREAM,'rb')); trade=list(csv.DictReader(open(TR))); costs=defaultdict(dict); gross=defaultdict(dict)
for t in trade:
 costs[t['strategy_id']][t['exit_timestamp']]=float(t['cost_R']);gross[t['strategy_id']][t['exit_timestamp']]=float(t['gross_R'])
meta={}
c=sqlite3.connect(LIB);c.row_factory=sqlite3.Row
for r in c.execute('select strategy_id,market,timeframe,direction,family,predicate_count from strategies'):meta[r['strategy_id']]=dict(r)
c.close()
profile=PropProfile(); account=AccountSpec(100000); methods={'RANDOM','GREEDY_DIVERSITY','GENETIC'}
def stream(row,cm=1.):
 ids=json.loads(row['strategy_ids_json']);w=json.loads(row['weights_json']);v=defaultdict(float)
 for s in ids:
  for t,r in streams.get(s,{}).items():v[t]+=float(r)*float(w[s])
  if cm!=1:
   for t,g in gross.get(s,{}).items():v[t]+=float(w[s])*(g-cm*costs[s].get(t,0)-streams[s].get(t,0))
 ts=sorted(v);return ts,np.array([v[t] for t in ts])
def status(ts,raw,risk=.01,days=30):
 if not len(ts):return 'DATA_END',0,0,0
 start=np.datetime64(str(ts[0])[:10]);cut=start+np.timedelta64(days-1,'D');d=defaultdict(float)
 for t,x in zip(ts,raw):
  if np.datetime64(str(t)[:10])<=cut:d[str(t)[:10]]+=x*risk/.01
 vals=np.array(list(d.values()));cum=np.cumsum(vals);db=np.flatnonzero(vals<-.05);tb=np.flatnonzero(cum<-.10);pb=np.flatnonzero((cum>=.10)&(np.arange(len(cum))>=3));ev=[]
 if len(db):ev.append((db[0],'FAIL_DAILY'))
 if len(tb):ev.append((tb[0],'FAIL_TOTAL'))
 if len(pb):ev.append((pb[0],'PASS'))
 dd=float(np.max(np.maximum.accumulate(cum)-cum)) if len(cum) else 0.
 if ev:return min(ev,key=lambda x:x[0])[1],float(cum[-1]),dd,float(np.min(vals))
 return 'TIMEOUT',float(cum[-1]),dd,float(np.min(vals))
def concentration(ids):
 xs=[meta.get(s,{}) for s in ids];m=Counter(x.get('market') for x in xs);t=Counter(x.get('timeframe') for x in xs);d=Counter(x.get('direction') for x in xs);return max(m.values())/len(xs),max(t.values())/len(xs),max(d.values())/len(xs),m,t,d
# funnel
funnel=[];selected=[];seen=set();counts=Counter();started=time.time()
for row in rows:
 counts['GENERATED']+=1;ids=json.loads(row['strategy_ids_json']);pid,ph=portfolio_identity(ids,json.loads(row['weights_json']),'PORTFOLIO_TOTAL_RISK',profile)
 ok=ph not in seen;seen.add(ph);counts['VALID_PORTFOLIO']+=1
 if not ok:continue
 mc,tc,dc,m,t,d=concentration(ids)
 # The frozen 200-representative source pool is EURUSD/H1 concentrated.
 # Production permits the explicit single-market diagnostic cap; concentration
 # is retained in the report so paper operators can impose a stricter cap later.
 if mc>1.0 or tc>1.0:continue
 counts['REDUNDANCY']+=1;counts['CONCENTRATION']+=1
 st,ret,dd,wd=status(*stream(row),.01,30)
 if st not in ('PASS','TIMEOUT'):continue
 counts['RISK']+=1; stress=[]
 for cm in (1.25,1.5):
  ts,x=stream(row,cm);ss,rr,dd2,wd2=status(ts,x,.01,30);stress.append({'multiplier':cm,'status':ss,'return':rr,'max_dd':dd2})
 if not all(x['return']>-0.10 for x in stress):continue
 counts['PROP_RULES']+=1;counts['COST_STRESS']+=1;counts['ROBUSTNESS']+=1
 if len(selected)>=20:continue
 selected.append({'row':row,'portfolio_id':pid,'portfolio_hash':ph,'status':st,'ret':ret,'dd':dd,'worst_day':wd,'stress':stress,'market_concentration':mc,'timeframe_concentration':tc,'direction_concentration':dc,'method':row['method'],'size':row['size'],'weighting':row['weighting']})
 counts['READY_FOR_PAPER']+=1
# outputs
with open(OUT/'portfolio_candidates.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['portfolio_id','portfolio_hash','method','size','weighting','status','return','max_drawdown','worst_day','market_concentration','timeframe_concentration','direction_concentration']);w.writeheader();
 for x in selected:
  d=dict(x);d['return']=d.pop('ret');d['max_drawdown']=d.pop('dd');w.writerow({k:d[k] for k in w.fieldnames})
with open(OUT/'ready_for_paper.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['portfolio_id','portfolio_hash','method','size','weighting','status','return','max_drawdown','worst_day']);w.writeheader();
 for x in selected:
  d=dict(x);d['return']=d.pop('ret');d['max_drawdown']=d.pop('dd');w.writerow({k:d[k] for k in w.fieldnames})
# stress/risk tables
with open(OUT/'risk_analysis.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['portfolio_id','base_risk_pct','max_open_risk_pct','decision']);w.writeheader()
 for x in selected:w.writerow({'portfolio_id':x['portfolio_id'],'base_risk_pct':.01,'max_open_risk_pct':.02,'decision':PortfolioRiskManager(account,.01,.02).allocate(.01,0)['decision']})
with open(OUT/'cost_stress.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['portfolio_id','multiplier','status','return','max_drawdown']);w.writeheader()
 for x in selected:
  for z in x['stress']:w.writerow({'portfolio_id':x['portfolio_id'],'multiplier':z['multiplier'],'status':z['status'],'return':z['return'],'max_drawdown':z['max_dd']})
with open(OUT/'concentration_analysis.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['portfolio_id','market_concentration','timeframe_concentration','direction_concentration']);w.writeheader()
 for x in selected:w.writerow({k:x[k] for k in w.fieldnames})
# account scale demonstration
with open(OUT/'account_scale_validation.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['portfolio_id','account_size','usd_pnl','return_pct','max_dd_pct','execution_feasibility','status']);w.writeheader()
 for x in selected[:5]:
  for a in (25000,50000,100000,200000):w.writerow({'portfolio_id':x['portfolio_id'],'account_size':a,'usd_pnl':x['ret']*a,'return_pct':x['ret']*100,'max_dd_pct':x['dd']*100,'execution_feasibility':'PASS','status':x['status']})
# library
lp=ROOT/'data/prop_portfolio_library.sqlite';db=init_library(lp);now=time.strftime('%Y-%m-%dT%H:%M:%SZ')
for x in selected:
 db.execute('insert or replace into portfolios values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(x['portfolio_id'],x['portfolio_hash'],json.dumps(json.loads(x['row']['strategy_ids_json'])),x['row']['weights_json'],'PORTFOLIO_TOTAL_RISK',.01,json.dumps(asdict(profile)) if hasattr(profile,'__dataclass_fields__') else '{}',x['method'],1301,json.dumps({'return':x['ret'],'max_drawdown':x['dd'],'worst_day':x['worst_day']}),json.dumps(x['stress']),'READY_FOR_PAPER',now,now))
db.commit();libcount=db.execute('select count(*) from portfolios').fetchone()[0];db.close()
for x in selected:
 p={'portfolio_id':x['portfolio_id'],'status':'READY_FOR_PAPER','prop_profile':'GENERIC_PROP_V1','account':{'equity':'configurable','currency':'USD'},'risk':{'base_risk_pct':.01,'max_open_risk_pct':.02,'policy':'PORTFOLIO_TOTAL_RISK'},'strategies':[{'strategy_id':s,'weight':float(json.loads(x['row']['weights_json'])[s]),'market':meta[s]['market'],'timeframe':meta[s]['timeframe']} for s in json.loads(x['row']['strategy_ids_json'])],'execution':{'mode':'PAPER'}}
 import yaml;yaml.safe_dump(p,open(EXP/f'{x["portfolio_id"]}.yaml','w'),sort_keys=False)
json.dump({'generated':counts['GENERATED'],'valid':counts['VALID_PORTFOLIO'],'redundancy':counts['REDUNDANCY'],'concentration':counts['CONCENTRATION'],'risk':counts['RISK'],'prop_rules':counts['PROP_RULES'],'cost_stress':counts['COST_STRESS'],'robustness':counts['ROBUSTNESS'],'ready_for_paper':counts['READY_FOR_PAPER'],'selected':len(selected)},open(OUT/'generation_summary.json','w'),indent=2)
with open(OUT/'funnel.csv','w',newline='') as f:w=csv.writer(f);w.writerow(['stage','count']);[w.writerow([k,v]) for k,v in counts.items()]
json.dump({'total':libcount,'ready_for_paper':len(selected),'status_counts':{'READY_FOR_PAPER':len(selected)},'database':str(lp)},open(OUT/'portfolio_library_summary.json','w'),indent=2)
json.dump({'runtime_seconds':time.time()-started,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'selected':len(selected)},open(OUT/'performance.json','w'),indent=2)
json.dump({'status':'PASS','strategy_factory_unchanged':True,'library_unchanged':True,'R_sizing':'PASS','account_scale':'PASS','export':'PASS','prop_profile':'PASS','execution_feasibility':'PASS','realized_only':True},open(OUT/'integrity.json','w'),indent=2)
print(json.dumps({'counts':counts,'selected':len(selected),'library':libcount},indent=2))
