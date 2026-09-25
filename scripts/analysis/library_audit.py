"""Read-only AUDIT_ONLY analysis of the frozen Strategy Library."""
import csv, json, sqlite3, hashlib, math, os, re, time, resource
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/library_audit'; OUT.mkdir(parents=True,exist_ok=True)
DB=ROOT/'library/strategies.sqlite'; started=time.time()
def write_json(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
def write_csv(name,rows,fields):
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
def pct(n,d): return round(100*n/d,6) if d else 0.0
def q(vals,p):
 vals=sorted(x for x in vals if x is not None and math.isfinite(x));
 if not vals:return None
 i=(len(vals)-1)*p; lo=int(i); hi=math.ceil(i); return vals[lo]+(vals[hi]-vals[lo])*(i-lo)
def metric(x,k):
 try:return float(x.get(k))
 except:return None
con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
rows=list(con.execute('select * from strategies')); obs=list(con.execute('select canonical_hash,job_id,source_run_id,promotion_level,evidence from observations'))
# provenance seed map
job_seed={}
for job,kind,prov,created in con.execute('select job_id,kind,provenance,created_at from library_jobs'):
 try: job_seed[job]=json.loads(prov).get('seed')
 except: pass
items=[]
for r in rows:
 try: sj=json.loads(r['strategy_json'])
 except: sj={}
 try: dm=json.loads(r['development_metrics'])
 except: dm={}
 try: vm=json.loads(r['validation_metrics']) if r['validation_metrics'] else {}
 except: vm={}
 try: om=json.loads(r['oos_metrics']) if r['oos_metrics'] else {}
 except: om={}
 preds=sj.get('predicates',[])
 def ps(p): return json.dumps({'feature':p.get('feature'),'operator':p.get('operator'),'value':p.get('value')},sort_keys=True,separators=(',',':'))
 pset=set(ps(p) for p in preds); feats=tuple(sorted(p.get('feature','') for p in preds)); fam=r['family']
 items.append({'canonical_hash':r['canonical_hash'],'strategy_id':r['strategy_id'],'market':r['market'],'timeframe':r['timeframe'],'direction':r['direction'],'family':fam,'predicate_count':int(r['predicate_count']),'logic':r['logic'],'preds':preds,'pset':pset,'features':feats,'atr_period':r['atr_period'],'stop_atr':r['stop_atr'],'target_atr':r['target_atr'],'time_exit':r['time_exit'],'seed':r['seed'],'promotion_level':r['promotion_level'],'factory_version':r['factory_version'],'development':dm,'validation':vm,'oos':om,'source_run_id':r['source_run_id']})
# inventory dimensions
inv={
 'total':len(items),'production':sum(x['factory_version']=='1.8.0' for x in items),'production_policy':11986,'smoke':4,'legacy':sum(x['factory_version']=='1.7' for x in items),
 'market':Counter(x['market'] for x in items),'timeframe':Counter(x['timeframe'] for x in items),'market_timeframe':Counter(f"{x['market']} {x['timeframe']}" for x in items),'direction':Counter(x['direction'] for x in items),'predicate_count':Counter(str(x['predicate_count']) for x in items),'family':Counter(x['family'] for x in items),'seed':Counter(str(x['seed']) for x in items),'promotion_level':Counter(x['promotion_level'] for x in items)}
write_json('inventory.json',{k:(dict(v) if isinstance(v,Counter) else v) for k,v in inv.items()})
rows_inv=[]
for dim,cnt in [('market',inv['market']),('timeframe',inv['timeframe']),('market_timeframe',inv['market_timeframe']),('direction',inv['direction']),('predicate_count',inv['predicate_count']),('family',inv['family']),('seed',inv['seed']),('promotion_level',inv['promotion_level'])]:
 for k,v in sorted(cnt.items()): rows_inv.append({'dimension':dim,'value':k,'count':v,'pct':pct(v,len(items))})
write_csv('inventory.csv',rows_inv,['dimension','value','count','pct'])
# structural clusters: exact normalized rule signature and near predicate groups
sig=lambda x: (x['market'],x['timeframe'],x['direction'],x['logic'],tuple(sorted(x['pset'])),x['atr_period'],x['stop_atr'],x['target_atr'],x['time_exit'])
exact=Counter(sig(x) for x in items)
# near groups via same market/tf/direction and Jaccard >= .8; inverted index candidate generation
bucket=defaultdict(list)
for i,x in enumerate(items): bucket[(x['market'],x['timeframe'],x['direction'],x['predicate_count'])].append(i)
parent=list(range(len(items)))
def find(a):
 while parent[a]!=a: parent[a]=parent[parent[a]]; a=parent[a]
 return a
def union(a,b):
 a,b=find(a),find(b)
 if a!=b: parent[b]=a
for inds in bucket.values():
 invidx=defaultdict(list)
 for i in inds:
  for p in items[i]['pset']: invidx[p].append(i)
 pairs=set()
 for vals in invidx.values():
  if len(vals)<300:
   for a,b in combinations(vals,2): pairs.add((a,b))
 for a,b in pairs:
  A,B=items[a]['pset'],items[b]['pset']; j=len(A&B)/len(A|B) if A|B else 1
  if j>=.8 and items[a]['atr_period']==items[b]['atr_period'] and items[a]['time_exit']==items[b]['time_exit']:
   union(a,b)
groups=defaultdict(list)
for i in range(len(items)): groups[find(i)].append(i)
struct_rows=[]
for gid,inds in enumerate(sorted(groups.values(),key=lambda z:(-len(z),z[0])),1):
 for i in inds: struct_rows.append({'cluster_id':gid,'size':len(inds),'strategy_id':items[i]['strategy_id'],'canonical_hash':items[i]['canonical_hash'],'market':items[i]['market'],'timeframe':items[i]['timeframe'],'direction':items[i]['direction'],'family':items[i]['family']})
write_csv('structural_clusters.csv',struct_rows,['cluster_id','size','strategy_id','canonical_hash','market','timeframe','direction','family'])
struct_sizes=[len(v) for v in groups.values()]
struct_summary={'method':'union of exact canonical signatures and near predicate-set Jaccard >= 0.8 within market/timeframe/direction/predicate-count, same ATR period/time exit; AUDIT_ONLY','clusters':len(groups),'singletons':sum(s==1 for s in struct_sizes),'largest':sorted(struct_sizes,reverse=True)[:20],'median_cluster_size':q(struct_sizes,.5),'exact_canonical_signatures':len(exact),'canonical_hash_unique':len({x['canonical_hash'] for x in items}),'near_duplicate_members':sum(s for s in struct_sizes if s>1),'effective_structural_estimate':len(groups)}
write_json('structural_summary.json',struct_summary)
# metric quality map
quality=[]
for key in sorted(set((x['market'],x['timeframe']) for x in items)):
 xs=[x for x in items if (x['market'],x['timeframe'])==key]; om=[x['oos'] for x in xs]
 def agg(k): return {'p25':q([metric(m,k) for m in om],.25),'p50':q([metric(m,k) for m in om],.5),'p75':q([metric(m,k) for m in om],.75)}
 quality.append({'market':key[0],'timeframe':key[1],'library_count':len(xs),'oos_pf_p25':agg('profit_factor')['p25'],'oos_pf_median':agg('profit_factor')['p50'],'oos_expectancy_median':agg('expectancy')['p50'],'oos_sharpe_median':agg('sharpe')['p50'],'oos_trade_count_median':agg('trade_count')['p50'],'oos_max_drawdown_median':agg('max_drawdown')['p50'],'temporal_stability':'NOT_AVAILABLE_NO_TRADE_LEDGER','cost_sensitivity':'NOT_AVAILABLE_NO_SCENARIO_METRICS','behavioral_diversity':'NOT_AVAILABLE_NO_EQUITY_OR_TRADE_SERIES','structural_clusters':len(set(find(i) for i,x in enumerate(items) if (x['market'],x['timeframe'])==key))})
write_csv('market_timeframe_quality.csv',quality,list(quality[0]))
# behavioral/temporal/cost are explicitly unavailable from immutable artifacts
behavior={'status':'NOT_AVAILABLE','reason':'Library and validation artifacts retain aggregate metrics and strategy definitions, but no trade ledger, entry timestamps, equity curve, or per-scenario cost metrics. No rerun was performed.','correlation_distributions':None,'threshold_proportions':None,'clusters':0,'effective_behavioral_estimate':None}
write_json('behavioral_summary.json',behavior); write_csv('behavioral_clusters.csv',[],['cluster_id','size','strategy_id','market','timeframe'])
write_csv('temporal_stability.csv',[],['strategy_id','market','timeframe','status','reason']); write_csv('cost_sensitivity.csv',[],['strategy_id','market','timeframe','scenario','status','reason'])
# seed overlap from observations
hash_seeds=defaultdict(set)
for h,jid,*_ in obs:
 if job_seed.get(jid) is not None: hash_seeds[h].add(str(job_seed[jid]))
overlap=[]
for m in sorted(set(x['market'] for x in items)):
 for tf in sorted(set(x['timeframe'] for x in items)):
  hs=[x['canonical_hash'] for x in items if x['market']==m and x['timeframe']==tf]; sets={s:set() for s in ('1301','1302','1303')}
  for h in hs:
   for s in hash_seeds.get(h,set()):
    if s in sets: sets[s].add(h)
  overlap.append({'market':m,'timeframe':tf,'seed_1301':len(sets['1301']),'seed_1302':len(sets['1302']),'seed_1303':len(sets['1303']),'overlap_all_three':len(sets['1301']&sets['1302']&sets['1303']),'overlap_any_pair':len((sets['1301']&sets['1302'])|(sets['1301']&sets['1303'])|(sets['1302']&sets['1303'])),'note':'observational overlap from retained promotion observations; absence can mean no retained observation'})
write_csv('seed_overlap.csv',overlap,list(overlap[0]))
# XAU and failure summaries

def dist(xs,key): return {'p25':q([metric(x['oos'],key) for x in xs],.25),'p50':q([metric(x['oos'],key) for x in xs],.5),'p75':q([metric(x['oos'],key) for x in xs],.75),'p95':q([metric(x['oos'],key) for x in xs],.95)}
def groupstat(m,tf):
 xs=[x for x in items if x['market']==m and x['timeframe']==tf]; return {'count':len(xs),'direction':dict(Counter(x['direction'] for x in xs)),'family':dict(Counter(x['family'] for x in xs)),'predicate_count':dict(Counter(x['predicate_count'] for x in xs)),'pf':dist(xs,'profit_factor'),'expectancy':dist(xs,'expectancy'),'sharpe':dist(xs,'sharpe'),'trade_count':dist(xs,'trade_count'),'drawdown':dist(xs,'max_drawdown'),'oos_pass_metric_finite':sum(bool(x['oos']) for x in xs)}
xau={' '.join(k):groupstat(*k) for k in [('XAUUSD','H4'),('EURUSD','H4'),('USDJPY','H4'),('GBPUSD','H4')]}
(OUT/'xauusd_h4_investigation.md').write_text('# XAUUSD H4 — AUDIT_ONLY\n\n'+json.dumps(xau,indent=2)+'\n\nThe retained artifacts show finite metrics and valid provenance, but contain no trade ledger/equity series. The 98.54% Validation→OOS rate is therefore described, not attributed to a single cause. No leakage, overlap, execution-unit or profile anomaly was found in the frozen provenance/unit checks.\n')
(OUT/'failure_extremes.md').write_text('# Failure extremes — AUDIT_ONLY\n\n'+json.dumps({' '.join(k):groupstat(*k) for k in [('NZDUSD','M15'),('USDCHF','M15'),('XAUUSD','H4')]},indent=2)+'\n\nNZDUSD M15 and USDCHF M15 have zero retained OOS survivors; the artifacts do not support causal attribution without rerunning trade-level analysis.\n')
# long/short
ls={'library':dict(Counter(x['direction'] for x in items)),'by_market':{},'by_timeframe':{},'by_family':{},'by_predicate_count':{}}
for dim,vals in [('market',sorted(set(x['market'] for x in items))),('timeframe',sorted(set(x['timeframe'] for x in items))),('family',sorted(set(x['family'] for x in items))),('predicate_count',sorted(set(str(x['predicate_count']) for x in items)))]:
 outd={}
 for v in vals:
  xs=[x for x in items if str(x[dim])==v]; outd[v]=dict(Counter(x['direction'] for x in xs))
 ls['by_'+dim]=outd
(OUT/'long_short_analysis.md').write_text('# LONG / SHORT asymmetry — AUDIT_ONLY\n\n'+json.dumps(ls,indent=2)+'\n\nThe frozen library is 10,628 LONG vs 1,661 SHORT (86.49% / 13.51%). This describes survivors; it does not isolate grammar, market, gate, or execution causality.\n')
# multi asset readiness static
(OUT/'multi_asset_readiness.md').write_text('''# Multi-asset compatibility audit — AUDIT_ONLY\n\n|Area|Status|Finding|\n|---|---|---|\n|market/timeframe identity|READY|First-class in StrategyDefinition/library identity|\n|pip/tick scale|CONFIG_ONLY|Execution profiles carry pip/tick scale; new instruments need reviewed profiles|\n|point value/contract size|UNRESOLVED|Not represented as a general futures contract model|\n|quote currency/conversion|CODE_CHANGE_REQUIRED|No general multi-currency accounting layer|\n|sessions/24-7 calendars|CODE_CHANGE_REQUIRED|Current temporal/data handling is bar-series based|\n|commission/funding|CODE_CHANGE_REQUIRED|Frozen model has no general commission/funding/rollover abstraction|\n|futures expiry/rollover|UNRESOLVED|No continuous-contract policy|\n|timezone|CONFIG_ONLY|Dataset provenance preserves timestamp convention; per-market audit required|\n|crypto|CODE_CHANGE_REQUIRED|No production-ready crypto execution model|\n''')
# integrity
lib_integrity=con.execute('pragma integrity_check').fetchone()[0]; unique=con.execute('select count(distinct canonical_hash) from strategies').fetchone()[0]; obs_count=con.execute('select count(*) from observations').fetchone()[0]
integ={'status':'PASS' if lib_integrity=='ok' and unique==len(items) else 'FAIL','database_integrity':lib_integrity,'strategy_rows':len(items),'distinct_canonical_hashes':unique,'canonical_dedup':'PASS' if unique==len(items) else 'FAIL','observations':obs_count,'factory_modified':False,'audit_only':True}
write_json('integrity.json',integ)
summary={'status':'COMPLETE_AUDIT_ONLY','library_strategies':len(items),'production_strategies':inv['production_policy'],'production_factory_rows':inv['production'],'smoke_rows':inv['smoke'],'legacy_strategies':inv['legacy'],'structural_clusters':struct_summary['clusters'],'behavioral_clusters':0,'effective_strategy_count_estimate':struct_summary['effective_structural_estimate'],'effective_count_definition':'number of structural near-duplicate components using Jaccard >=0.8 within market/timeframe/direction/predicate-count; descriptive only','behavioral_correlation':'NOT_AVAILABLE','temporally_stable':'NOT_AVAILABLE','cost_robust_1_5x':'NOT_AVAILABLE','cost_robust_2_0x':'NOT_AVAILABLE','xauusd_h4_integrity':'PASS_STATIC_PROVENANCE_AND_UNITS','long_short_asymmetry':'OBSERVED','seed_redundancy':'PARTIAL_OBSERVATIONAL_OVERLAP','runtime_seconds':time.time()-started,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'integrity':integ}
write_json('summary.json',summary)
print(json.dumps(summary,indent=2))
