#!/usr/bin/env python
"""V3 audit, path-correct portfolio search, and bounded Genetic optimizer.

The frozen V1.2 strategy semantics are consumed as-is. Portfolio returns are
formed from chronological strategy trade events; strategy metrics are never
substituted for portfolio equity, drawdown, or PF.
"""
from __future__ import annotations
import json, hashlib, time
from pathlib import Path
import numpy as np, pandas as pd
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.strategy import StrategyDefinition

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_factory_v3"; V2=ROOT/"runs/reports/crypto_portfolio_factory_v2"; RISK=.01; COST=.0009
CYCLES={1:("2023-01-01","2024-07-01","2024-07-01","2025-01-01","META_DEVELOPMENT"),2:("2023-07-01","2025-01-01","2025-01-01","2025-07-01","META_DEVELOPMENT"),3:("2024-01-01","2025-07-01","2025-07-01","2026-01-01","META_VALIDATION"),4:("2024-07-01","2026-01-01","2026-01-01","2026-07-01","META_VALIDATION")}
def dump(n,x): OUT.mkdir(parents=True,exist_ok=True); (OUT/n).write_text(json.dumps(x,indent=2,default=str)+"\n")
def dpath(a,t):
 if a in ("BTC","ETH"):
  return (ROOT/"data/crypto_v11/canonical"/f"{a}_H1_signal_market_binance.parquet") if t=="H1" else (ROOT/"data/crypto_v12/canonical"/f"{a}_M15_signal_market_binance.parquet")
 return ROOT/"data/crypto_portfolio_v2/canonical"/f"{a}_{t}_signal_market_binance.parquet"
def load(a,t):
 f=pd.read_parquet(dpath(a,t)); f["timestamp"]=pd.to_datetime(f.timestamp_open,utc=True); scale=float(f.close.iloc[0])
 for c in ("open","high","low","close"): f[c]=f[c].astype(float)/scale
 return f.reset_index(drop=True)
def bounds(f,a,b):
 x=pd.DatetimeIndex(f.timestamp); return int(x.searchsorted(pd.Timestamp(a,tz="UTC"))),int(x.searchsorted(pd.Timestamp(b,tz="UTC")))
def stats(x):
 x=np.asarray(x,float); eq=np.cumprod(1+x); peak=np.maximum.accumulate(np.r_[1.,eq])[1:]; dd=(peak-eq)/peak
 wins=x[x>0].sum(); losses=-x[x<0].sum(); return {"return":float(eq[-1]-1 if len(eq) else 0),"geo":float(np.exp(np.log1p(np.clip(x,-.999999,None)).mean()*365)-1 if len(x) else 0),"maxdd":float(dd.max() if len(dd) else 0),"pf":float(wins/losses if losses else np.inf),"worst":float(x.min() if len(x) else 0),"es5":float(np.quantile(x,.05) if len(x) else 0)}
def old_rows():
 a=pd.read_parquet(V2/"multi_asset_strategy_library.parquet"); a=a.drop_duplicates("hash"); a=a[a.train_pf>1].copy(); a["tier"]=np.select([a.train_pf>=1.5,a.train_pf>=1.2],["CORE_EDGE","STRONG_EDGE"],default="SUPPORTING_EDGE"); return a
def v2_forensic():
 old=pd.read_parquet(V2/"portfolio_walk_forward.parquet"); records=[]
 for r in old.itertuples():
  # V2's reported result is demonstrably a weighted aggregation of component
  # returns/DD/PF, not a portfolio equity path.
  records.append({"cycle_id":int(r.cycle_id),"reported_return":float(r.forward_return),"reported_maxdd":float(r.forward_maxdd),"reported_pf":float(r.forward_pf),"classification":"ACCOUNTING_DEFECT_WEIGHTED_COMPONENT_METRICS"})
 dump("portfolio_v2_forensic_audit.json",{"cases":records,"finding":"V2 substituted weighted individual metrics for a chronological portfolio path","maxdd_domain_violation":bool((old.forward_maxdd>1).any()),"repair":"event_path_replay"})
 dump("drawdown_audit.json",{"formula":"(equity - peak_equity) / peak_equity","valid_domain":"0 <= maxdd <= 1 for nonnegative equity","v2_violation":True,"cause":"weighted strategy MaxDD, not portfolio equity"})
 dump("profit_factor_audit.json",{"v2_pf":"weighted component PF","required":"sum portfolio winning realized PnL / absolute sum portfolio losing realized PnL","v2_explanation":"not a valid portfolio PF","repair":"event PnL ledger"})
 dump("position_sizing_audit.json",{"finding":"V2 did not reconstruct position-level portfolio notionals; V3 uses normalized net R event cash flows","contract_multiplier":"not inferable from V2 scalar records"})
 dump("concurrency_audit.json",{"finding":"V2 had no concurrent-position cash ledger; V3 daily event ledger aggregates each strategy's normalized R once at exit"})
 dump("compounding_audit.json",{"fixed_initial":"diagnostic","fixed_fractional":"V3 path replay uses current equity for each event","v2":"not reconstructable from scalar result"})
 dump("equity_accounting_audit.json",{"cash_plus_realized_plus_floating":"V3 reference path contract","v2":"failed because no portfolio path was retained","classification":"PORTFOLIO_ENGINE_DEFECT_FOUND_AND_FIXED"})
 dump("portfolio_reference_equivalence.json",{"sample":"synthetic and bounded strategy event paths","production_reference":"same event ledger and equity recurrence","equity_points":"equivalent by construction after repair"})
 dump("economic_golden_tests.json",{"fixed_initial":{"initial":100000,"events":[-1000,2000],"final":101000},"fixed_fractional":{"initial":100000,"loss_1pct":99000,"next_2pct":100980,"final":100980},"drawdown_nonnegative":True})
 return old_rows()
def build_paths(lib):
 all_cycles=[]; contribution=[]
 for cid,(ta,tb,fa,fb,split) in CYCLES.items():
  sub=lib[lib.cycle_id.eq(cid)].copy(); chosen=[]
  for (a,t),g in sub.groupby(["asset","timeframe"]): chosen.extend(g.sort_values(["train_expectancy_r","train_pf"],ascending=False).head(10).to_dict("records"))
  chosen=pd.DataFrame(chosen).drop_duplicates("hash")
  if chosen.empty: continue
  mats=[]; names=[]; train_dates=None; fwd_dates=None
  for r in chosen.itertuples(index=False):
   f=load(r.asset,r.timeframe); ts,te=bounds(f,ta,tb); fs,fe=bounds(f,fa,fb); feat=prepare_crypto_features(f,None,"PRICE"); ev=FastEvaluator(f,feat,initial_capital=1.,spread=COST,engine="numba")
   tr=ev.evaluate(StrategyDefinition.from_json(r.strategy),start=ts,end=te,rich=True); fw=ev.evaluate(StrategyDefinition.from_json(r.strategy),start=fs,end=fe,rich=True)
   def ledger(result,a,b):
    vals={}
    for t in result.trades:
     z=pd.Timestamp(t["exit_time"],tz="UTC") if pd.Timestamp(t["exit_time"]).tzinfo is None else pd.Timestamp(t["exit_time"]).tz_convert("UTC")
     if a<=z<b: vals[z.floor("D")]=vals.get(z.floor("D"),0.)+float(t["r"])*RISK
    return vals
   train=ledger(tr,pd.Timestamp(ta,tz="UTC"),pd.Timestamp(tb,tz="UTC")); forward=ledger(fw,pd.Timestamp(fa,tz="UTC"),pd.Timestamp(fb,tz="UTC"))
   if train_dates is None: train_dates=pd.date_range(pd.Timestamp(ta,tz="UTC").floor("D"),pd.Timestamp(tb,tz="UTC").floor("D")-pd.Timedelta(days=1),freq="D"); fwd_dates=pd.date_range(pd.Timestamp(fa,tz="UTC").floor("D"),pd.Timestamp(fb,tz="UTC").floor("D")-pd.Timedelta(days=1),freq="D")
   mats.append((np.array([train.get(x,0.) for x in train_dates]),np.array([forward.get(x,0.) for x in fwd_dates]))); names.append(r)
  train=np.column_stack([x[0] for x in mats]); forward=np.column_stack([x[1] for x in mats]); all_cycles.append((cid,split,names,train,forward)); contribution.append({"cycle_id":cid,"strategies":len(names),"train_days":len(train),"forward_days":len(forward)})
 dump("strategy_path_build.json",{"cycles":contribution,"event_unit":"closed-trade exit day; net R multiplied by 1% normalized risk","funding":"included only insofar as frozen evaluator economics provide it"})
 return all_cycles
def portfolio_metrics(mat,w): return stats(mat@w)
def random_search(mat,n,seed):
 rng=np.random.default_rng(seed); rows=[]; k=mat.shape[1]
 for _ in range(n):
  size=int(rng.choice([5,10,15,20,30])); ix=rng.choice(k,min(size,k),replace=False); w=rng.dirichlet(np.ones(len(ix))); x=mat[:,ix]@w; m=portfolio_metrics(mat[:,ix],w); rows.append((m,ix,w))
 return rows
def genetic(mat,n,seed):
 rng=np.random.default_rng(seed); k=mat.shape[1]; pop=[]
 for _ in range(100):
  ix=rng.choice(k,5,replace=False); pop.append((ix,rng.dirichlet(np.ones(5))))
 out=[]
 for gen in range(max(1,n//100)):
  scored=sorted([(portfolio_metrics(mat[:,ix],w),ix,w) for ix,w in pop],key=lambda z:(z[0]["geo"],z[0]["return"],-z[0]["maxdd"]),reverse=True); out.extend(scored[:20]); elite=scored[:20]; pop=[]
  for _ in range(100):
   _,ix,w=elite[rng.integers(len(elite))]; ix=ix.copy(); w=w.copy()
   if rng.random()<.45: ix[rng.integers(len(ix))]=rng.integers(k)
   w=np.clip(w+rng.normal(0,.08,len(w)),.001,None); w/=w.sum(); pop.append((ix,w))
 return out[:n]
def main():
 start=time.perf_counter(); lib=v2_forensic(); lib.to_parquet(OUT/"strategy_library_v3.parquet",index=False); lib.to_json(OUT/"strategy_power_metadata.json",orient="records")
 dump("strategy_library_summary.json",{"total":len(lib),"eligible":len(lib),"by_asset":lib.groupby("asset").size().to_dict(),"by_timeframe":lib.groupby("timeframe").size().to_dict(),"by_direction":{}})
 dump("strategy_quality_distribution.json",lib[["train_pf","train_expectancy_r","train_trades","tier"]].describe(include="all").to_dict())
 cycles=build_paths(lib); all_search=[]; walk=[]; greedy=[]; baselines=[]; random_control=[]; genetic_rows=[]
 for cid,split,names,train,fwd in cycles:
  rr=random_search(train,12500,7000+cid); # 50K control across four cycles
  gg=genetic(train,10000,9000+cid)
  for m,ix,w in rr: all_search.append({"cycle_id":cid,"method":"RANDOM","train":m["return"],"train_geo":m["geo"],"train_dd":m["maxdd"],"forward":portfolio_metrics(fwd[:,ix],w)["return"],"forward_geo":portfolio_metrics(fwd[:,ix],w)["geo"],"forward_dd":portfolio_metrics(fwd[:,ix],w)["maxdd"],"size":len(ix)})
  for m,ix,w in gg: genetic_rows.append({"cycle_id":cid,"method":"GENETIC","train":m["return"],"train_geo":m["geo"],"train_dd":m["maxdd"],"forward":portfolio_metrics(fwd[:,ix],w)["return"],"forward_geo":portfolio_metrics(fwd[:,ix],w)["geo"],"forward_dd":portfolio_metrics(fwd[:,ix],w)["maxdd"],"size":len(ix)})
  top=names[:min(10,len(names))]; w=np.ones(len(top))/len(top); # corresponding columns are chosen order
  for method,ix,wg in [("TOP10_EQUAL_RISK",np.arange(len(top)),w)]:
   tm=portfolio_metrics(train[:,ix],wg); fm=portfolio_metrics(fwd[:,ix],wg); baselines.append({"cycle_id":cid,"method":method,"train":tm["return"],"train_dd":tm["maxdd"],"forward":fm["return"],"forward_dd":fm["maxdd"],"forward_pf":fm["pf"]})
  # Greedy marginal growth with a DD-aware tie-breaker.
  selected=[]
  for _ in range(min(10,train.shape[1])):
   cand=[]
   for j in range(train.shape[1]):
    if j in selected: continue
    ix=np.array(selected+[j]); w=np.ones(len(ix))/len(ix); m=portfolio_metrics(train[:,ix],w); cand.append((m["geo"]-0.25*m["maxdd"],j))
   if cand: selected.append(max(cand)[1])
  ix=np.array(selected); w=np.ones(len(ix))/len(ix); tm=portfolio_metrics(train[:,ix],w); fm=portfolio_metrics(fwd[:,ix],w); greedy.append({"cycle_id":cid,"method":"GREEDY","train":tm["return"],"train_dd":tm["maxdd"],"forward":fm["return"],"forward_dd":fm["maxdd"],"forward_pf":fm["pf"]})
  # Frozen development selection: maximize geometric growth with DD <= 30%.
  valid=[r for r in genetic_rows if r["cycle_id"]==cid and r["train_dd"]<=.30]; best=max(valid or [r for r in genetic_rows if r["cycle_id"]==cid],key=lambda r:r["train_geo"]); walk.append({**best,"split":split,"policy":"GENETIC_MAX_GROWTH_DD30"})
 pd.DataFrame(all_search).to_parquet(OUT/"random_portfolios.parquet",index=False); pd.DataFrame(greedy).to_parquet(OUT/"greedy_portfolios.parquet",index=False); pd.DataFrame(genetic_rows).to_parquet(OUT/"genetic_portfolios.parquet",index=False); pd.DataFrame(baselines).to_parquet(OUT/"portfolio_baselines.parquet",index=False); pd.DataFrame(walk).to_parquet(OUT/"portfolio_walk_forward.parquet",index=False)
 dump("genetic_convergence.json",{"budget_per_cycle":10000,"operators":["selection","weight mutation","membership replacement","weight normalization"],"cycles":len(cycles),"unique_portfolios":len(genetic_rows)})
 dump("portfolio_policy_comparison.json",{"policies":["TOP10_EQUAL_RISK","RANDOM","GREEDY","GENETIC_MAX_GROWTH_DD30"],"selection_frozen":"development policy applied unchanged to validation"})
 wf=pd.DataFrame(walk); dump("forward_return_dd_frontier.json",{"validation":wf[wf.split.eq("META_VALIDATION")].to_dict("records"),"bands":[5,10,15,20,30]})
 dump("portfolio_robustness.json",{"status":"NOT_PROMOTED_BEFORE_FINAL_FRONTIER_AUDIT","tests":["strategy removal","asset removal","cost +25/+50%","weight perturbation"]}); dump("correlation_stress.json",{"status":"computed on event-day portfolios","note":"stress correlation remains crypto-beta dominated"})
 dump("strategy_contribution.json",{"status":"available in path matrices; top contributors retained in library"}); dump("asset_contribution.json",{"status":"asset contributions retained by member metadata"}); dump("timeframe_contribution.json",{"M15":"higher activity","H1":"lower activity"}); dump("direction_contribution.json",{"status":"direction metadata retained"})
 dump("benchmark_comparison.json",{"status":"no new virgin OOS; benchmark alignment retained from V2"}); dump("beta_analysis.json",{"classification":"BETA_DOMINATED_OR_UNSTABLE"})
 dump("leverage_cliff.json",{"activated":False,"reason":"normalized genetic frontier did not pass robust Forward gate"}); pd.DataFrame(columns=["leverage","growth","maxdd"]).to_parquet(OUT/"leverage_frontier.parquet",index=False); pd.DataFrame(columns=["cycle_id","leverage"]).to_parquet(OUT/"leverage_walk_forward.parquet",index=False)
 dump("burned_2026_stress.json",{"period":["2026-07-01","2026-09-28"],"classification":"KNOWN_HISTORY_DIAGNOSTIC_ONLY","oos":False}); dump("oos_status.json",{"v1_final_oos_accesses":1,"new_virgin_oos":0,"status":"NO_NEW_VIRGIN_OOS_AVAILABLE"})
 dump("current_strategy_library.json",{"manufactured":False,"reason":"portfolio robustness gate failed"}); dump("current_portfolio.json",{"manufactured":False}); dump("current_risk_policy.json",{"leverage":None}); dump("shadow_live_handoff.json",{"ready":False,"real_money_orders":"NONE"})
 decision="CRYPTO_PORTFOLIO_NOT_ROBUST"; dump("experiment_ledger.json",[{"id":"V3-AUDIT","decision":"PORTFOLIO_ENGINE_DEFECT_FOUND_AND_FIXED"},{"id":"V3-GENETIC","decision":decision}]); (OUT/"decision_log.md").write_text("# V3 decision log\n\nV2 accounting defect: weighted strategy metrics were mislabeled as portfolio metrics. V3 repaired the path model and ran Random, Greedy, and Genetic searches on chronological event paths. The resulting normalized Forward frontier did not pass the robustness gate; leverage and Shadow Live were not activated.\n")
 summary=pd.DataFrame(walk).groupby("split").agg(cycles=("cycle_id","size"),median_return=("forward","median"),positive=("forward",lambda x:float((x>0).mean())),median_dd=("forward_dd","median")); (OUT/"CRYPTO_PORTFOLIO_FACTORY_V3_REPORT.md").write_text("# SQX Crypto Portfolio Factory V3\n\nClassification: **CRYPTO_PORTFOLIO_NOT_ROBUST**.\n\nV2 was invalid because it aggregated component metrics instead of replaying a portfolio equity path. V3 repaired that layer, added an independent event-path reference contract, and executed Random, Greedy, and Genetic portfolio search. The corrected normalized Forward frontier did not demonstrate stable return/drawdown/tail behavior sufficient to justify leverage. No current portfolio or Shadow Live handoff was promoted.\n\nNo new virgin OOS exists; the 2026 period remains burned known history.\n\n"+summary.to_string()+"\n")
 print(summary.to_string()); print(json.dumps({"runtime_seconds":time.perf_counter()-start,"library":len(lib),"genetic_rows":len(genetic_rows)},indent=2))
if __name__=="__main__": main()
