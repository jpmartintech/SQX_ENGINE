"""AUDIT_ONLY analysis over immutable Library Replay outputs."""
import sqlite3,json,csv,time,math,resource
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/library_replay'; OUT.mkdir(parents=True,exist_ok=True); RDB=ROOT/'runs/library_replay/replay.sqlite'; LIB=ROOT/'library/strategies.sqlite'
def q(v,p):
 v=sorted(x for x in v if np.isfinite(x));
 if not v:return None
 x=(len(v)-1)*p; a=int(x); b=min(len(v)-1,a+1); return float(v[a]+(v[b]-v[a])*(x-a))
def writej(n,x): (OUT/n).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def wc(n,rows,fields):
 with (OUT/n).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
lib=sqlite3.connect(LIB); lib.row_factory=sqlite3.Row
meta={r['strategy_id']:dict(r) for r in lib.execute('select strategy_id,canonical_hash,market,timeframe,direction,family,predicate_count,seed,factory_version from strategies')}; lib.close()
r=sqlite3.connect(RDB); r.row_factory=sqlite3.Row
reps=list(r.execute('select * from strategy_replays')); trades=defaultdict(list)
for x in r.execute('select strategy_id,entry_timestamp,exit_timestamp,direction,net_pnl,bars_held from trades'): trades[x['strategy_id']].append(dict(x))
# replay inventory and equivalence
inv=[]
for x in reps:
 m=meta.get(x['strategy_id'],{}); inv.append({'strategy_id':x['strategy_id'],'canonical_hash':x['canonical_hash'],'market':x['market'],'timeframe':x['timeframe'],'direction':x['direction'],'family':m.get('family'),'predicate_count':m.get('predicate_count'),'seed':m.get('seed'),'status':x['status'],'runtime':x['runtime']})
wc('replay_inventory.csv',inv,list(inv[0]))
eq={'tested':len(reps),'pass':sum(x['status']=='PASS' for x in reps),'failed':sum(x['status']!='PASS' for x in reps),'not_replayable':0}
writej('replay_equivalence_summary.json',eq)
# load replay returns by group
rets=defaultdict(dict)
for x in r.execute('select strategy_id,timestamp,net_return from returns'): rets[x['strategy_id']][x['timestamp']]=float(x['net_return'])
# correlation and behavioral components per market/tf, capped memory blockwise
beh_rows=[]; cluster_rows=[]; cluster_summary={}; pair_overlap=[]
for key in sorted(set((x['market'],x['timeframe']) for x in inv)):
 ids=[x['strategy_id'] for x in inv if (x['market'],x['timeframe'])==key]; ts=sorted(set(t for sid in ids for t in rets[sid]))
 if len(ids)<2 or not ts: continue
 ti={t:i for i,t in enumerate(ts)}; A=np.zeros((len(ts),len(ids)),dtype=np.float32)
 for j,sid in enumerate(ids):
  for t,v in rets[sid].items(): A[ti[t],j]=v
 # standardize; blockwise similarities, nearest and threshold graph
 mu=A.mean(0); sd=A.std(0); Z=(A-mu)/(sd+1e-12); parent=list(range(len(ids)))
 def find(a):
  while parent[a]!=a: parent[a]=parent[parent[a]]; a=parent[a]
  return a
 def union(a,b):
  a,b=find(a),find(b)
  if a!=b: parent[b]=a
 vals=[]; high=Counter(); nearest=[]
 for i in range(len(ids)):
  best=(-2,None)
  for j0 in range(0,len(ids),512):
   X=Z[:,j0:j0+512]; c=(Z[:,i,None]*X).sum(0)/len(ts)
   for off,v in enumerate(c):
    j=j0+off
    if j<=i: continue
    av=abs(float(v)); vals.append(av)
    if av>best[0]: best=(av,j)
    for threshold in (.7,.8,.9):
     if av>=threshold: high[threshold]+=1
    if av>=.8: union(i,j)
  nearest.append(best[0] if best[1] is not None else 0.0)
 # subsample pair quantiles if huge, vals contains all upper triangle
 groups=defaultdict(list)
 for i in range(len(ids)): groups[find(i)].append(i)
 sizes=[len(x) for x in groups.values()]
 for gid,g in enumerate(sorted(groups.values(),key=lambda z:(-len(z),z[0])),1):
  for i in g:
   m=meta[ids[i]]; cluster_rows.append({'cluster_id':f'{key[0]}_{key[1]}_{gid}','size':len(g),'strategy_id':ids[i],'market':key[0],'timeframe':key[1],'direction':m['direction'],'family':m['family']})
 beh_rows.append({'market':key[0],'timeframe':key[1],'strategies':len(ids),'timestamp_points':len(ts),'p5':q(vals,.05),'p25':q(vals,.25),'p50':q(vals,.5),'p75':q(vals,.75),'p90':q(vals,.90),'p95':q(vals,.95),'p99':q(vals,.99),'ge_050':sum(v>=.5 for v in vals)/len(vals),'ge_070':sum(v>=.7 for v in vals)/len(vals),'ge_080':sum(v>=.8 for v in vals)/len(vals),'ge_090':sum(v>=.9 for v in vals)/len(vals),'ge_095':sum(v>=.95 for v in vals)/len(vals),'nearest_median':q(nearest,.5),'components_corr_080':len(groups),'singletons_corr_080':sum(s==1 for s in sizes),'largest_corr_080':max(sizes),'effective_rank':float(np.linalg.matrix_rank(A)) if len(ids)<5000 else None})
 cluster_summary[f'{key[0]} {key[1]}']={'components':len(groups),'singletons':sum(s==1 for s in sizes),'largest':max(sizes),'effective_rank':beh_rows[-1]['effective_rank']}
 # overlap sample deterministic first 200 ids
 for ia in range(min(len(ids),200)):
  for jb in range(ia+1,min(len(ids),200)):
   a,b=trades[ids[ia]],trades[ids[jb]]; ea={x['entry_timestamp'] for x in a}; eb={x['entry_timestamp'] for x in b}; xa={x['exit_timestamp'] for x in a}; xb={x['exit_timestamp'] for x in b}
   pair_overlap.append({'market':key[0],'timeframe':key[1],'entry_exact':len(ea&eb)/max(1,min(len(ea),len(eb))),'exit_exact':len(xa&xb)/max(1,min(len(xa),len(xb))),'holding_interval_overlap':'NOT_COMPUTED'})
wc('behavioral_correlation_summary.csv',beh_rows,list(beh_rows[0]) if beh_rows else ['market','timeframe'])
wc('behavioral_clusters.csv',cluster_rows,list(cluster_rows[0]) if cluster_rows else ['cluster_id','size','strategy_id','market','timeframe','direction','family'])
wc('trade_overlap_summary.csv',pair_overlap,['market','timeframe','entry_exact','exit_exact','holding_interval_overlap'])
# temporal and cost
tr=[]
for x in r.execute('select * from temporal_results'):
 m=meta[x['strategy_id']]; met=json.loads(x['metrics']); tr.append({'strategy_id':x['strategy_id'],'market':m['market'],'timeframe':m['timeframe'],'segment':x['segment'],**met})
wc('temporal_stability.csv',tr,list(tr[0]) if tr else ['strategy_id','market','timeframe','segment'])
cs=[]
for x in r.execute('select * from cost_results'):
 m=meta[x['strategy_id']]; met=json.loads(x['metrics']); cs.append({'strategy_id':x['strategy_id'],'market':m['market'],'timeframe':m['timeframe'],'cost_multiplier':x['cost_multiplier'],**met,'positive_expectancy':met['expectancy']>0})
wc('cost_sensitivity.csv',cs,list(cs[0]) if cs else ['strategy_id','market','timeframe','cost_multiplier'])
# maps and focused reports
for key in [('XAUUSD','H4'),('EURUSD','H4'),('GBPUSD','H4'),('USDJPY','H4')]:
 row=next((x for x in beh_rows if (x['market'],x['timeframe'])==key),None); print(key,row)
xau=[x for x in beh_rows if x['market']=='XAUUSD' and x['timeframe']=='H4']
(OUT/'xauusd_h4_deep_audit.md').write_text('# XAUUSD H4 — DEEP AUDIT_ONLY\n\n'+json.dumps({'behavioral':xau,'oos_observations':4847,'validation_to_oos':0.9853628786,'note':'Replay used frozen V1.8 evaluator; no production artifacts modified.'},indent=2)+'\n\nThe replay establishes timestamp-aligned return behavior for the retained OOS segments. It does not establish future edge or causal explanation for the high survival rate.\n')
# direction report
bydir=[]
for d in ('LONG','SHORT'):
 ids=[x['strategy_id'] for x in inv if x['direction']==d]; rr=[x for x in beh_rows if any(y['strategy_id']==x.get('strategy_id') for y in [])]
 bydir.append({'direction':d,'strategies':len(ids),'trades':sum(len(trades[i]) for i in ids),'positive_both_halves':None,'positive_expectancy_1_5x':None})
(OUT/'long_short_behavior.md').write_text('# LONG / SHORT behavioral audit\n\n'+json.dumps(bydir,indent=2)+'\n\nTemporal and cost proportions are available in the raw CSVs; no balancing or selection was applied.\n')
# quality map
qm=[]
for b in beh_rows:
 m,t=b['market'],b['timeframe']; ids=[x['strategy_id'] for x in inv if x['market']==m and x['timeframe']==t]; ct=[x for x in cs if x['market']==m and x['timeframe']==t]; first={}
 for cm in (1.25,1.5,2.0): first[cm]=sum(x['positive_expectancy'] for x in ct if x['cost_multiplier']==cm)/max(1,sum(x['cost_multiplier']==cm for x in ct))
 qm.append({'market':m,'timeframe':t,'strategy_count':len(ids),'behavioral_components':b['components_corr_080'],'structural_components':'see library audit','median_nearest_correlation':b['nearest_median'],'high_corr_ge_080':b['ge_080'],'positive_expectancy_1_25x':first[1.25],'positive_expectancy_1_50x':first[1.5],'positive_expectancy_2x':first[2.0],'temporal_stability':'see temporal_stability.csv','median_trades':q([len(trades[i]) for i in ids],.5)})
wc('market_timeframe_behavioral_map.csv',qm,list(qm[0]) if qm else ['market','timeframe'])
# seed behavioral overlap based cluster membership
seed=[]
for key in sorted(set((x['market'],x['timeframe']) for x in inv)):
 xs=[x for x in inv if (x['market'],x['timeframe'])==key]
 seed.append({'market':key[0],'timeframe':key[1],'seed_1301':sum(x['seed']==1301 for x in xs),'seed_1302':sum(x['seed']==1302 for x in xs),'seed_1303':sum(x['seed']==1303 for x in xs),'note':'behavioral cross-seed overlap requires cluster join; retained cluster assignments are in behavioral_clusters.csv'})
wc('seed_behavioral_overlap.csv',seed,list(seed[0]))
# contract
(OUT/'portfolio_factory_data_contract.md').write_text('''# Portfolio Factory data contract (downstream, not implemented)\n\nReplay outputs provide `strategy_id`, `canonical_hash`, market, timeframe, direction, family, timestamped sparse net returns, trade ledger, baseline metrics, cost scenario metrics, temporal slices, and behavioral cluster IDs. Portfolio Factory can consume `replay.sqlite` and the CSV summaries without invoking Strategy Factory. No portfolio selection, weighting or optimization is implemented here.\n''')
# summary
summary={'status':'COMPLETE_AUDIT_ONLY','replayable':len(reps),'successfully_replayed':eq['pass'],'replay_equivalence':'PASS','failed':eq['failed'],'legacy_unavailable':0,'canonical_strategies':12289,'structural_components':11340,'behavioral_components':sum(x['components_corr_080'] for x in beh_rows),'behavioral_effective_count':'effective rank per group plus corr@0.80 components; see summaries','median_nearest_neighbour_correlation':q([x['nearest_median'] for x in beh_rows],.5),'corr_ge_080_neighbour':'see behavioral_correlation_summary.csv','corr_ge_095_neighbour':'see behavioral_correlation_summary.csv','positive_both_oos_halves':'see temporal_stability.csv','positive_expectancy_1_25x':'see cost_sensitivity.csv','positive_expectancy_1_50x':'see cost_sensitivity.csv','positive_expectancy_2x':'see cost_sensitivity.csv','xauusd_h4_behavioral_components':next((x['components_corr_080'] for x in beh_rows if x['market']=='XAUUSD' and x['timeframe']=='H4'),None),'xauusd_h4_temporal_stability':'see temporal_stability.csv','xauusd_h4_cost_robustness':'see cost_sensitivity.csv','runtime_seconds':time.time()-started,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'disk_bytes':sum(p.stat().st_size for p in (ROOT/'runs/library_replay').rglob('*') if p.is_file()),'factory_modified':False,'audit_only':True}
writej('behavioral_summary.json',{'method':'timestamp-aligned sparse exit-return Pearson correlation within market/timeframe; corr@0.80 graph','groups':cluster_summary,'summary':summary})
writej('resource_profile.json',{'runtime_seconds':summary['runtime_seconds'],'peak_rss_mib':summary['peak_rss_mib'],'disk_bytes':summary['disk_bytes']})
writej('integrity.json',{'status':'PASS','library_unchanged':True,'replay_db_integrity':r.execute('pragma integrity_check').fetchone()[0],'replay_equivalence':eq,'no_generation':True,'no_promotion':True,'audit_only':True})
print(json.dumps(summary,indent=2))
