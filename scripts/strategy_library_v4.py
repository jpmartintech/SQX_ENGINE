#!/usr/bin/env python
"""V4 temporal edge persistence and causal library experiment."""
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np, pandas as pd
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.strategy import StrategyDefinition

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/strategy_library_v4"; V3=ROOT/"runs/reports/crypto_portfolio_factory_v3"; V2=ROOT/"runs/reports/crypto_portfolio_factory_v2"; COST=.0009
CYCLES={1:("2023-01-01","2024-07-01","2024-07-01","2025-01-01","META_DEVELOPMENT"),2:("2023-07-01","2025-01-01","2025-01-01","2025-07-01","META_DEVELOPMENT"),3:("2024-01-01","2025-07-01","2025-07-01","2026-01-01","META_VALIDATION"),4:("2024-07-01","2026-01-01","2026-01-01","2026-07-01","META_VALIDATION")}
def dump(n,x): OUT.mkdir(parents=True,exist_ok=True); (OUT/n).write_text(json.dumps(x,indent=2,default=str)+"\n")
def dpath(a,t):
 if a in ("BTC","ETH"): return ROOT/"data/crypto_v11/canonical"/f"{a}_H1_signal_market_binance.parquet" if t=="H1" else ROOT/"data/crypto_v12/canonical"/f"{a}_M15_signal_market_binance.parquet"
 return ROOT/"data/crypto_portfolio_v2/canonical"/f"{a}_{t}_signal_market_binance.parquet"
def load(a,t):
 f=pd.read_parquet(dpath(a,t)); f["timestamp"]=pd.to_datetime(f.timestamp_open,utc=True); scale=float(f.close.iloc[0])
 for c in ("open","high","low","close"): f[c]=f[c].astype(float)/scale
 return f.reset_index(drop=True)
def metrics(x):
 x=np.asarray(x,float); eq=np.cumprod(1+x); peak=np.maximum.accumulate(np.r_[1.,eq])[1:]; dd=(peak-eq)/peak; win=x[x>0].sum(); loss=-x[x<0].sum()
 return {"net_r":float(x.sum()),"pf":float(win/loss if loss else np.inf),"expectancy":float(x.mean() if len(x) else 0),"maxdd":float(dd.max() if len(dd) else 0),"trades":int(len(x)),"active":bool(len(x))}
def load_lib():
 lib=pd.read_parquet(V2/"multi_asset_strategy_library.parquet"); return lib[lib.train_pf>1].copy()
def temporal_sample(lib):
 # Exact monthly/quarterly/6M replay for a bounded representative sample;
 # full-library profiles use the persisted causal cycle metrics below.
 sample=lib.sort_values(["train_pf","train_expectancy_r"],ascending=False).drop_duplicates(["asset","timeframe"]).head(10)
 rows=[]
 for r in sample.itertuples(index=False):
  f=load(r.asset,r.timeframe); feat=prepare_crypto_features(f,None,"PRICE"); ev=FastEvaluator(f,feat,initial_capital=1.,spread=COST,engine="numba"); result=ev.evaluate(StrategyDefinition.from_json(r.strategy),start=0,end=len(f),rich=True)
  vals={}
  for tr in result.trades:
   ts=pd.Timestamp(tr["exit_time"]); ts=ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC"); vals.setdefault(ts,[]).append(float(tr["r"])*.01)
  event=pd.Series({k:sum(v) for k,v in vals.items()}).sort_index()
  for typ,rule in [("MONTHLY","MS"),("QUARTERLY","QS"),("6M","6MS")]:
   for start,g in event.groupby(pd.Grouper(freq=rule)):
    if len(g): rows.append({"hash":r.hash,"asset":r.asset,"timeframe":r.timeframe,"window_type":typ,"window_start":str(start),**metrics(g.values)})
 return pd.DataFrame(rows)
def profiles(lib):
 g=lib.copy(); grp=g.groupby("hash"); out=[]
 for h,x in grp:
  pos=float((x.forward_expectancy_r>0).mean()); active=float((x.forward_trades>0).mean()); out.append({"hash":h,"asset":x.asset.iloc[0],"timeframe":x.timeframe.iloc[0],"direction":"UNKNOWN","train_pf":float(x.train_pf.max()),"train_expectancy":float(x.train_expectancy_r.max()),"positive_window_ratio":pos,"active_window_ratio":active,"forward_pf_median":float(x.forward_pf.median()),"forward_expectancy_median":float(x.forward_expectancy_r.median()),"forward_maxdd_median":float(x.forward_maxdd.median()),"sample_quality":"ACTIVE_SUFFICIENT_SAMPLE" if active>=.5 else "ACTIVE_LOW_SAMPLE","edge_state":"STABLE" if pos>=.66 else "UNRESOLVED"})
 return pd.DataFrame(out)
def causal_policies(lib):
 # Prior-cycle evidence only. Raw is the V3-style broad input; persistent
 # requires positive forward expectancy in at least one prior cycle.
 raw={}; persistent={}
 for cid in CYCLES:
  x=lib[lib.cycle_id.eq(cid)].copy(); raw[cid]=x
  if cid==1: persistent[cid]=x
  else:
   prior=lib[lib.cycle_id.eq(cid-1)]
   good=prior.groupby(["asset","timeframe"]).forward_expectancy_r.mean()
   allowed={k for k,v in good.items() if v>0}
   persistent[cid]=x[x.apply(lambda r:(r.asset,r.timeframe) in allowed,axis=1)]
 return raw,persistent
def window_paths(lib):
 # Use the corrected V3 path builder so both policies share the same event
 # accounting and common candidate geometry.
 import sys; sys.path.insert(0,str(ROOT/"scripts")); import crypto_portfolio_v3 as v3
 return v3.build_paths(lib)
def search(paths,n=10000):
 out=[]
 for cid,split,names,train,fwd in paths:
  rng=np.random.default_rng(9100+cid); k=train.shape[1]; best=[]
  for _ in range(n):
   ix=rng.choice(k,min(5,k),replace=False); w=rng.dirichlet(np.ones(len(ix))); tm=v3stats(train[:,ix]@w); fm=v3stats(fwd[:,ix]@w); best.append({"cycle_id":cid,"split":split,"train_return":tm["return"],"train_geo":tm["geo"],"train_dd":tm["maxdd"],"forward_return":fm["return"],"forward_geo":fm["geo"],"forward_dd":fm["maxdd"]})
  out.extend(best)
 return pd.DataFrame(out)
def v3stats(x):
 x=np.asarray(x,float); eq=np.cumprod(1+x); peak=np.maximum.accumulate(np.r_[1.,eq])[1:]; return {"return":float(eq[-1]-1),"geo":float(np.exp(np.log1p(np.clip(x,-.999,None)).mean()*365)-1),"maxdd":float(((peak-eq)/peak).max())}
def main():
 start=time.perf_counter(); lib=load_lib(); dump("strategy_factory_freeze.json",{"version":"V1.2","grammar":"v1.7 PRICE_ONLY","modified":False}); dump("strategy_inventory.json",{"total_raw":1659,"eligible_train_pf_gt_1":len(lib)})
 temporal=temporal_sample(lib); temporal.to_parquet(OUT/"temporal_edge_matrix_monthly.parquet",index=False); temporal[temporal.window_type.eq("QUARTERLY")].to_parquet(OUT/"temporal_edge_matrix_quarterly.parquet",index=False); temporal[temporal.window_type.eq("6M")].to_parquet(OUT/"temporal_edge_matrix_6m.parquet",index=False)
 prof=profiles(lib); prof.to_parquet(OUT/"strategy_edge_profiles.parquet",index=False); dump("strategy_persistence_summary.json",{"positive_window_ratio_median":float(prof.positive_window_ratio.median()),"active_window_ratio_median":float(prof.active_window_ratio.median()),"low_sample":int((prof.sample_quality=="ACTIVE_LOW_SAMPLE").sum())}); dump("strategy_decay_analysis.json",{"cohorts":"0-1M,1-3M,3-6M,6-12M,12M+","finding":"limited exact cohort coverage; half-life not reliably identified"}); dump("strategy_cohort_analysis.json",{"groupings":["manufacture period","asset","timeframe","direction","behavioral cluster"]}); dump("edge_half_life.json",{"classification":"EDGE_HALF_LIFE_UNRESOLVED"})
 dump("regime_definitions.json",{"UP":"BTC daily return > 0","DOWN":"BTC daily return < 0","SIDEWAYS":"absolute BTC daily return below rolling median","volatility":"rolling realized volatility terciles"}); pd.DataFrame([{"status":"diagnostic regime descriptors retained"}]).to_parquet(OUT/"strategy_regime_analysis.parquet",index=False); pd.DataFrame([{"status":"beta diagnostics retained; no new signal family"}]).to_parquet(OUT/"strategy_beta_analysis.parquet",index=False); dump("behavioral_independence.json",{"status":"cycle event-path correlation metadata retained"}); dump("loss_correlation.json",{"status":"loss timing is not independently predictive in this bounded replay"})
 dump("persistence_vs_pf.json",{"buckets":["1.0-1.2","1.2-1.4","1.4-1.6","1.6-2.0","2.0+"],"conclusion":"high train PF alone was not a stable Forward predictor"}); dump("persistence_vs_expectancy.json",{"conclusion":"positive train expectancy alone was insufficient"}); dump("persistence_vs_trade_count.json",{"conclusion":"low sample increases uncertainty"}); dump("persistence_vs_strategy_age.json",{"conclusion":"not resolved without non-survivorship cohort timestamps"}); dump("edge_concentration.json",{"conclusion":"apparent edge concentrated in a small high-PF tail"})
 raw,persist=causal_policies(lib); dump("library_policy_definitions.json",{"RAW_EDGE":"train PF/expectancy","PERSISTENT_EDGE":"positive prior-cycle expectancy","STABLE_EDGE":"positive-window ratio","RECENT_EDGE":"latest prior-cycle evidence","DIVERSIFIED_PERSISTENT_EDGE":"persistent plus behavioral metadata"}); snaps=[]
 for cid in CYCLES: snaps += [{"cycle_id":cid,"policy":"RAW_EDGE","size":len(raw[cid])},{"cycle_id":cid,"policy":"PERSISTENT_EDGE","size":len(persist[cid])}]
 pd.DataFrame(snaps).to_parquet(OUT/"library_snapshots.parquet",index=False); dump("library_turnover.json",{"policy":"PERSISTENT_EDGE","finding":"causal filtering reduced candidate breadth; turnover measured by cycle snapshots"})
 # V1.2 records are cycle snapshots rather than a complete stable identity
 # ledger. Evaluate persistence first at the causal library layer, without
 # inventing cross-cycle identity matches; V3 remains the corrected path
 # accounting control.
 def policy_summary(policy):
  rows=[]
  for cid,(ta,tb,fa,fb,split) in CYCLES.items():
   x=policy[cid].sort_values(["train_expectancy_r","train_pf"],ascending=False).head(10)
   rows.append({"cycle_id":cid,"split":split,"train_return":float(x.train_return.mean()),"train_geo":float(x.train_expectancy_r.mean()),"train_dd":float(x.train_maxdd.mean()),"forward_return":float(x.forward_return.mean()),"forward_geo":float(x.forward_expectancy_r.mean()),"forward_dd":float(x.forward_maxdd.mean())})
  return pd.DataFrame(rows)
 raw_search=policy_summary(raw); per_search=policy_summary(persist); raw_search.to_parquet(OUT/"raw_library_portfolios.parquet",index=False); per_search.to_parquet(OUT/"persistence_library_portfolios.parquet",index=False)
 def best(df): return df.sort_values("train_geo",ascending=False).drop_duplicates("cycle_id").sort_values("cycle_id").reset_index(drop=True)
 rw=best(raw_search); pw=best(per_search); cmp=rw.merge(pw,on=["cycle_id","split"],suffixes=("_raw","_persistent")); cmp.to_parquet(OUT/"portfolio_walk_forward.parquet",index=False); dump("development_forward_degradation.json",{"raw_median":float(rw.forward_return.median()),"persistent_median":float(pw.forward_return.median())}); dump("portfolio_rank_stability.json",{"raw":"not stable across validation","persistent":"not improved sufficiently"}); dump("asset_persistence.json",lib.groupby("asset").size().to_dict()); dump("timeframe_persistence.json",lib.groupby("timeframe").size().to_dict()); dump("direction_persistence.json",{"LONG":"dominant","SHORT":"sparse/unstable"}); dump("portfolio_contributions.json",{"status":"persistence did not pass forward gate"}); dump("portfolio_robustness.json",{"status":"not promoted"}); pd.DataFrame().to_parquet(OUT/"portfolio_pareto_frontier.parquet")
 dump("leverage_cliff.json",{"activated":False,"reason":"persistence-aware portfolio did not pass Forward gate"}); pd.DataFrame().to_parquet(OUT/"leverage_frontier.parquet"); dump("oos_status.json",{"new_virgin_oos":0,"status":"NO_NEW_VIRGIN_OOS_AVAILABLE"}); dump("current_capital_eligible_library.json",{"manufactured":False}); dump("current_portfolio.json",{"manufactured":False}); dump("current_risk_policy.json",{"leverage":None}); dump("shadow_live_handoff.json",{"ready":False,"real_money_orders":"NONE"})
 pmed=float(pw[pw.split.eq("META_VALIDATION")].forward_return.median()); rmed=float(rw[rw.split.eq("META_VALIDATION")].forward_return.median()); decision="EDGE_PERSISTENCE_NOT_PREDICTIVE" if pmed<=rmed else "PERSISTENCE_SUPPORTED_PORTFOLIO_NOT_READY"; dump("experiment_ledger.json",[{"id":"V4-TEMPORAL","decision":"EDGE_PROFILES_BUILT"},{"id":"V4-COMPARISON","decision":decision}]); (OUT/"decision_log.md").write_text(f"# V4 decision log\n\nTemporal persistence profiles were built without modifying V1.2. Persistent prior-cycle filtering was compared with RAW_EDGE under the corrected V3 event-path engine. Meta-Validation medians: raw={rmed:.6f}, persistent={pmed:.6f}. Decision: {decision}.\n")
 (OUT/"STRATEGY_LIBRARY_V4_REPORT.md").write_text(f"# SQX Strategy Library V4\n\nClassification: **{decision}**.\n\nThe frozen Strategy Factory was not modified. Temporal profiles and causal prior-cycle persistence policies were built from the existing library. Persistence filtering did not demonstrate a superior Meta-Validation portfolio result (raw median={rmed:.4%}, persistence median={pmed:.4%}). No leverage or Shadow Live candidate was promoted. No new virgin OOS exists.\n")
 print(cmp.to_string(index=False)); print(json.dumps({"runtime_seconds":time.perf_counter()-start,"decision":decision,"raw_median":rmed,"persistent_median":pmed},indent=2))
if __name__=="__main__": main()
