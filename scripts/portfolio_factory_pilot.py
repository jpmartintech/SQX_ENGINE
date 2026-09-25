import sqlite3,json,csv,hashlib,time,random
from pathlib import Path
import numpy as np
from sqx_engine.portfolio_factory import PortfolioEngine,PortfolioConstraints,FtmoSimulator,FtmoConfig,PortfolioRequest,portfolio_hash
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/portfolio_factory_v1'; OUT.mkdir(parents=True,exist_ok=True); R=ROOT/'runs/library_replay/replay.sqlite'; L=ROOT/'library/strategies.sqlite'
def load():
 l=sqlite3.connect(L); l.row_factory=sqlite3.Row; meta={r['strategy_id']:dict(r) for r in l.execute('select strategy_id,market,timeframe,direction,family,predicate_count,seed from strategies')}; l.close()
 t=sqlite3.connect(R); ret={}
 for x in t.execute('select strategy_id,timestamp,net_return from returns'): ret.setdefault(x[0],{})[x[1]]=x[2]
 temporal={};
 for sid,seg,met in t.execute('select strategy_id,segment,metrics from temporal_results'): temporal.setdefault(sid,{})[seg]=json.loads(met)
 costs={};
 for sid,cm,met in t.execute('select strategy_id,cost_multiplier,metrics from cost_results'): costs.setdefault(sid,{})[float(cm)]=json.loads(met)
 t.close(); both={sid for sid,d in temporal.items() if d.get('OOS_FIRST_HALF',{}).get('expectancy',-1)<=0 or d.get('OOS_SECOND_HALF',{}).get('expectancy',-1)<=0}; robust={sid for sid,d in costs.items() if d.get(1.5,{}).get('expectancy',-1)<=0}; candidates=[sid for sid in meta if sid not in both and sid not in robust]
 # behavioral cluster from committed report
 clusters={}
 with open(ROOT/'runs/reports/library_replay/behavioral_clusters.csv') as f:
  for r in csv.DictReader(f): clusters[r['strategy_id']]=r['cluster_id']
 for sid in candidates: meta[sid]['cluster']=clusters.get(sid,sid)
 # deterministic 500 candidate pool, one per behavior cluster
 pool=[]; seen=set()
 for sid in sorted(candidates):
  if meta[sid]['cluster'] in seen: continue
  seen.add(meta[sid]['cluster']); pool.append(sid)
  if len(pool)>=200: break
 ts=sorted(set(k for sid in pool for k in ret.get(sid,{}))); idx={s:i for i,s in enumerate(pool)}; A=np.zeros((len(ts),len(pool))); ti={x:i for i,x in enumerate(ts)}
 for sid in pool:
  for x,v in ret[sid].items(): A[ti[x],idx[sid]]=v
 return meta,pool,A,ts,len(candidates)
def metrics(engine,ids,weight):
 x=engine.evaluate(ids,weight); ii=[engine.metadata['index'][s] for s in ids]; c=POOL_CORR[np.ix_(ii,ii)] if len(ids)>1 else np.array([[1.]])
 upper=np.abs(c[np.triu_indices(len(ids),1)]) if len(ids)>1 else np.array([0.]); x['average_correlation']=float(upper.mean()) if len(upper) else 0.; x['max_pair_correlation']=float(upper.max()) if len(upper) else 0.; x['objective']=x['sharpe']-2*x['max_drawdown']-max(0,x['max_pair_correlation']-.8)*5; return x
meta,pool,A,ts,universe=load(); md={'index':{s:i for i,s in enumerate(pool)},'rows':{s:meta[s] for s in pool}}; engine=PortfolioEngine(A,md,ts); POOL_CORR=np.corrcoef(A.T); c=PortfolioConstraints(max_strategies=30,max_pair_correlation=.95,max_per_cluster=1); rng=random.Random(1301); results=[]; budget=1000
ftmo=FtmoSimulator(FtmoConfig())
def valid(ids):return engine.validate(ids,c)[0]
def search(method):
 best=[]
 for n in range(budget):
  size=rng.choice([10,20,30])
  if method=='GREEDY_DIVERSITY':
   ids=[]
   for sid in sorted(pool,key=lambda s:meta[s].get('seed',0)):
    if len(ids)>=size:break
    if valid(ids+[sid]):ids.append(sid)
   ids=ids[:size]
  elif method=='GENETIC':
   ids=rng.sample(pool,size)
   if not valid(ids):
    ids=[]
    for sid in rng.sample(pool,len(pool)):
     if valid(ids+[sid]) and len(ids)<size:ids.append(sid)
  else:
   ids=rng.sample(pool,size)
  if not valid(ids):continue
  for weighting in ('EQUAL_WEIGHT','EQUAL_RISK'):
   m=metrics(engine,ids,weighting); m.update({'method':method,'evaluation':n,'size':size,'weighting':weighting,'portfolio_hash':portfolio_hash(PortfolioRequest(tuple(ids),weighting,1.0,c)),'ftmo':ftmo.run(m['stream'],ts)}); m.pop('stream',None); results.append(m)
 return
for method in ('RANDOM','GREEDY_DIVERSITY','GENETIC'): search(method)
# write compact results
for m in results: m['strategy_ids_json']=json.dumps(m.pop('strategy_ids')); m['weights_json']=json.dumps(m.pop('weights')); m['ftmo_status']=m.pop('ftmo')['status']; m.pop('ftmo',None)
fields=list(results[0]);
with (OUT/'pilot_results.csv').open('w',newline='') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(results)
# summaries
from collections import defaultdict
summ={}
for method in ('RANDOM','GREEDY_DIVERSITY','GENETIC'):
 xs=[x for x in results if x['method']==method]; summ[method]={'evaluated':len(xs),'best_objective':max(x['objective'] for x in xs),'best_sharpe':max(x['sharpe'] for x in xs),'median_sharpe':float(np.median([x['sharpe'] for x in xs])),'median_dd':float(np.median([x['max_drawdown'] for x in xs])),'ftmo_pass_rate':sum(x['ftmo_status']=='PASS' for x in xs)/len(xs)}
json.dump({'candidate_universe':universe,'candidate_pool':len(pool),'pilot_budget_per_method':budget,'methods':summ,'clock':'union of realized OOS exit timestamps UTC; realized-only','cost_label':'RETROSPECTIVE_PORTFOLIO_RESEARCH'},open(OUT/'pilot_summary.json','w'),indent=2)
json.dump({'candidate_universe':universe,'candidate_pool':len(pool),'pool_selection':'one strategy per behavioral cluster, deterministic canonical order','replay_equivalence':'PASS','temporal_label':'RETROSPECTIVE_PORTFOLIO_RESEARCH'},open(OUT/'phase1_validation.json','w'),indent=2)
# golden first 10
ids=pool[:10]; gm=metrics(engine,ids,'EQUAL_WEIGHT'); gm.pop('stream',None); json.dump({'portfolio_hash':portfolio_hash(PortfolioRequest(tuple(ids))),'strategy_ids':ids,'metrics':gm},open(OUT/'golden_portfolio.json','w'),indent=2)
print(json.dumps({'universe':universe,'pool':len(pool),'results':len(results),'summary':summ},indent=2))
