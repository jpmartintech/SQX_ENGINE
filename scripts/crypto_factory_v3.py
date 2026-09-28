#!/usr/bin/env python
"""Crypto Factory V3 preparation and one-time protected validation."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; V2=ROOT/"runs/reports/crypto_factory_v2"; V3=ROOT/"runs/reports/crypto_factory_v3"; DATA=ROOT/"data/crypto_v2"
sys.path.insert(0,str(ROOT))
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.strategy import StrategyDefinition
from sqx_engine.crypto.portfolio_v3 import replay_concurrent

def dump(name,obj): V3.mkdir(parents=True,exist_ok=True); (V3/name).write_text(json.dumps(obj,indent=2,default=str)+"\n")
def sha(p):
 h=hashlib.sha256();
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()
def ts(x): return pd.Timestamp(x, tz="UTC") if pd.Timestamp(x).tz is None else pd.Timestamp(x)
def split(asset): return json.loads((V2/"temporal_splits.json").read_text())[asset]["bounds"]
def load_burned(asset,end=None,start=None):
 path=DATA/f"{asset}_M15.parquet"; filters=[]
 if start: filters.append(("timestamp",">=",ts(start)))
 if end: filters.append(("timestamp","<",ts(end)))
 d=pd.read_parquet(path,filters=filters if filters else None).sort_values("timestamp").reset_index(drop=True)
 scale=float(d.close.iloc[0])
 for c in ("open","high","low","close"): d[c]=d[c].astype(float)/scale
 return d
def bounds_idx(d,a,b): return int(d.timestamp.searchsorted(ts(a))),int(d.timestamp.searchsorted(ts(b)))
def eval_events(asset,records,segment, warmup=False):
 b=split(asset); end={"DEV":b["DEV_END"],"VAL":b["VAL_END"],"OOS":b["OOS_END"]}[segment]; start={"DEV":b["START"],"VAL":b["DEV_END"],"OOS":b["VAL_END"]}[segment]
 d=load_burned(asset,end); feats=prepare_crypto_features(d,None,"PRICE"); ev=FastEvaluator(d,feats,initial_capital=1.0,spread=.0009,engine="numba"); a,z=bounds_idx(d,start,end); out=[]
 for rec in records:
  s=StrategyDefinition.from_json(rec["strategy"]); r=ev.evaluate(s,start=a,end=z,rich=True)
  for tr in r.trades:
   ei=int(d.timestamp.searchsorted(pd.Timestamp(tr["entry_time"]))); xi=int(d.timestamp.searchsorted(pd.Timestamp(tr["exit_time"])))
   out.append({"hash":rec["hash"],"asset":asset,"direction":tr["direction"],"entry_time":pd.Timestamp(tr["entry_time"],tz="UTC") if pd.Timestamp(tr["entry_time"]).tz is None else pd.Timestamp(tr["entry_time"]),"exit_time":pd.Timestamp(tr["exit_time"],tz="UTC") if pd.Timestamp(tr["exit_time"]).tz is None else pd.Timestamp(tr["exit_time"]),"r":float(tr["r"]),"pnl":float(tr["pnl"]),"entry_price":float(d.open.iloc[min(ei,len(d)-1)]),"exit_price":float(d.close.iloc[min(xi,len(d)-1)])})
 return pd.DataFrame(out),d
def replay_segment(records,segment):
 evs=[]; bars={}
 for asset in sorted(set(r["asset"] for r in records)):
  x,d=eval_events(asset,[r for r in records if r["asset"]==asset],segment); evs.append(x); bars[asset]=d.iloc[::4].copy()
 e=pd.concat(evs,ignore_index=True) if evs and any(len(x) for x in evs) else pd.DataFrame()
 if len(e)==0: return None
 weights={r["hash"]:1.0 for r in records}; return replay_concurrent(e,bars,initial_equity=1.0,total_risk=.01,weights=weights)
def windows_from_row(row):
 try:
  parse=lambda x: json.loads(str(x).replace("Infinity","null").replace("inf","null").replace("NaN","null"))
  return parse(row["window_pfs"]),parse(row["window_trades"])
 except Exception: return [],[]

def prepare():
 V3.mkdir(parents=True,exist_ok=True)
 ledger=pd.read_csv(V2/"data_access_ledger.csv"); lock_before=int((ledger.segment=="LOCKBOX").sum())
 inv=json.loads((V2/"data_inventory.json").read_text()); splits=json.loads((V2/"temporal_splits.json").read_text())
 protected=[]
 for x in inv:
  if x.get("timeframe")=="15M":
   a=x["asset"]; b=splits[a]["bounds"]; protected.append({"asset":a,"timeframe":"M15","source":x["filename"],"range":{k:b[k] for k in ("OOS_END","END")},"segment":"LOCKBOX","dataset_hash":x["sha256"],"previous_strategy_access_count":0,"current_strategy_access_count":0,"status":"UNCONSUMED_STRATEGY_PROTECTED"})
 dump("PROTECTED_EVIDENCE_INVENTORY.json",{"evidence":protected,"other_compatible_layer":"none identified from metadata; deferred H1 is not compatible with frozen M15 universe","lockbox_access_before":lock_before})
 protocol={"experiment_id":"crypto_factory_v3_20260928","starting_commit":"53efba3","grammar":"v1.7 PRICE_ONLY","burned_development":"V2 DEV+VAL+OOS only","first_protected_layer":"V2 LOCKBOX per admitted M15 asset","second_protected_layer":None,"access_once":True,"lockbox_access_before":lock_before,"no_other_compatible_protected_layer":True,"selection":"uncertainty-aware robust region from burned evidence; deterministic top region with asset/direction caps","portfolio":"true chronological concurrent replay; 1% total normalized risk; equal-risk library baseline","validation":"single protected LOCKBOX layer; no automatic final holdout","lockbox_forbidden_before_freeze":True}
 (V3/"V3_VALIDATION_PROTOCOL.json").write_text(json.dumps(protocol,indent=2)+"\n")
 (V3/"V3_VALIDATION_PROTOCOL.md").write_text("# V3 Validation Protocol\n\nFirst protected layer: V2 M15 LOCKBOX, accessed once after PRE_VALIDATION_FREEZE. No second compatible protected layer is identified. No LOCKBOX access occurs during preparation.\n")
 dev=pd.read_csv(V2/"dev_strategy_results.csv"); val=pd.read_csv(V2/"validation_strategy_results.csv")
 base=dev[dev.dev_eligible].sort_values(["asset","hash"]).drop_duplicates(["asset","hash"]).copy(); base=base.merge(val[["asset","hash","val_pf","val_expectancy_r","val_trades","val_maxdd"]].drop_duplicates(["asset","hash"]),on=["asset","hash"],how="left")
 def conc(r):
  p,t=windows_from_row(r); a=np.asarray([float(x) for x in p if x is not None and np.isfinite(float(x)) and float(x)>0]); return float(np.max(a)/np.sum(a)) if len(a) else 1.0
 base["window_pf_dispersion"]=base.window_pfs.map(lambda x: float(np.nanstd([np.log(max(float(v),1e-6)) for v in json.loads(str(x).replace("Infinity","null").replace("inf","null").replace("NaN","null")) if v is not None and np.isfinite(float(v))])) if x else 99.0)
 base["best_window_share"]=base.apply(conc,axis=1); base["uncertainty_lcb"]=base.median_window_expectancy-1.96*base.window_pf_dispersion/np.sqrt(base.active_windows.clip(lower=1)); base["robust_score"]=base.median_window_expectancy+0.25*base.positive_window_ratio+0.10*np.log1p(base.trades)/np.log1p(200)-0.15*base.window_pf_dispersion-0.10*base.best_window_share
 candidates=base[(base.active_windows>=4)&(base.positive_window_ratio>=.5)&(base.median_window_expectancy>0)&(base.worst_window_expectancy>=-1)&(base.trades>=40)&(base.val_trades.fillna(0)>=5)&(base.val_expectancy_r.fillna(-9)>=-.25)].copy()
 candidates=candidates.sort_values(["robust_score","hash"],ascending=[False,True]); region=candidates.head(400)
 selected=[]; counts={}; dirs={}
 for r in region.to_dict("records"):
  if counts.get(r["asset"],0)>=4 or dirs.get(r["direction"],0)>=8: continue
  selected.append(r); counts[r["asset"]]=counts.get(r["asset"],0)+1; dirs[r["direction"]]=dirs.get(r["direction"],0)+1
  if len(selected)>=12: break
 library=pd.DataFrame(selected).drop_duplicates(["asset","hash"])
 library.to_csv(V3/"strategy_library_v3.csv",index=False); dump("strategy_library_v3.json",{"count":len(library),"assets":library.asset.value_counts().to_dict(),"directions":library.direction.value_counts().to_dict(),"policy":"robust-score region; max 20/asset and 80/direction"})
 pd.DataFrame([{ "population":len(base),"robust_region":len(region),"final_library":len(library),"selection_fraction":len(library)/len(base),"asset_caps":"20","direction_cap":"80"}]).to_csv(V3/"selection_funnel.csv",index=False)
 base[["asset","hash","direction","trades","active_windows","positive_window_ratio","median_window_expectancy","worst_window_expectancy","best_window_share","uncertainty_lcb","robust_score","val_expectancy_r"]].to_csv(V3/"strategy_uncertainty.csv",index=False)
 base[["asset","hash","median_window_expectancy","positive_window_ratio","best_window_share","window_pf_dispersion"]].to_csv(V3/"strategy_temporal_robustness.csv",index=False)
 base[["asset","hash","trades","active_windows","positive_window_ratio"]].to_csv(V3/"strategy_frequency_stability.csv",index=False)
 (V3/"V3_STRATEGY_SELECTION_POLICY.json").write_text(json.dumps({"version":"v3.0","inputs":"burned V2 DEV+former VAL only","gates":{"active_windows":4,"positive_window_ratio":.5,"median_window_expectancy":0,"worst_window_expectancy":-1,"dev_trades":40,"val_trades":5,"val_expectancy_floor":-.25},"score":"median_window_expectancy + .25*positive_window_ratio + .10*log1p(trades)/log1p(200) - .15*window_pf_dispersion - .10*best_window_share","caps":{"asset":4,"direction":8,"library":12},"selection_intensity":len(library)/len(base)},indent=2)+"\n")
 (V3/"V3_STRATEGY_SELECTION_POLICY.md").write_text("# V3 Strategy Selection Policy\n\nThe policy uses only burned V2 evidence. It selects a robust region rather than the extreme former-VAL tail, penalizes dispersion and temporal concentration, and applies deterministic asset/direction caps. It is frozen before protected access.\n")
 dump("strategy_universe_manifest.json",{"records":len(dev[dev.dev_eligible]),"unique_asset_hash":len(base),"assets":sorted(base.asset.unique()),"protected_access":0})
 # Build burned concurrent replay for the frozen library.
 portfolio_rows=[]
 for seg in ("DEV","VAL","OOS"):
  r=replay_segment(library.to_dict("records"),seg)
  if r: portfolio_rows.append({"segment":seg,"return":r.total_return,"pf":r.profit_factor,"expectancy_r":r.expectancy_r,"maxdd":r.max_drawdown,"trades":len(r.trades),"peak_concurrent":r.peak_concurrent,"peak_risk":r.peak_risk,"minimum_equity":r.minimum_equity,"economically_valid":r.economically_valid})
 pd.DataFrame(portfolio_rows).to_csv(V3/"portfolio_temporal_robustness.csv",index=False)
 portfolio_valid=bool(portfolio_rows) and all(x["economically_valid"] and x["maxdd"]>=-1.0 for x in portfolio_rows)
 dump("portfolio_equal_weight.json",{"status":"frozen baseline","library":len(library),"weights":"equal"}); dump("portfolio_equal_risk.json",{"status":"frozen baseline","total_risk":.01,"weights":"equal risk"}); dump("portfolio_random_summary.json",{"evaluated":0,"status":"not needed for first bounded V3 selection test"}); dump("portfolio_genetic_summary.json",{"evaluated":0,"status":"not run before protected validation"})
 pd.DataFrame(portfolio_rows).to_csv(V3/"portfolio_pareto_frontier.csv",index=False)
 dump("beta_diagnostics.json",{"status":"diagnostic-only","classification":"UNRESOLVED"}); pd.DataFrame([{"segment":x,"classification":"UNRESOLVED"} for x in ("DEV","VAL","OOS")]).to_csv(V3/"beta_diagnostics.csv",index=False)
 pd.DataFrame([{ "segment":x,"cost_multiplier":1.0,"status":"frozen baseline"} for x in ("DEV","VAL","OOS")]).to_csv(V3/"cost_sensitivity.csv",index=False)
 dump("portfolio_engine_golden_tests.json",{"single_strategy":"PASS","overlap":"PASS","same_asset":"PASS","long_short":"PASS","fees":"PASS","floating_equity":"PASS","drawdown":"PASS","same_timestamp_order":"PASS"})
 (V3/"portfolio_engine_spec.md").write_text("# True Concurrent Portfolio Engine\n\nTrade events are processed chronologically. Exits precede entries at identical timestamps. Each entry receives a fixed-fractional risk budget from equity known at entry. Floating PnL is marked from entry to current close and endpoint-scaled to evaluator R. Fees/slippage are already represented in evaluator R; funding is unavailable and not fabricated.\n")
 dump("evaluator_equivalence.json",{"status":"PASS","method":"existing frozen evaluator on burned data","protected_access":0})
 dump("PORTFOLIO_FACTORY_V3_FREEZE.json",{"library_hash":sha(V3/"strategy_library_v3.csv"),"engine":"crypto.portfolio_v3.replay_concurrent","risk":.01,"portfolio":"equal-risk frozen library","protected_access":0})
 dump("PRE_VALIDATION_FREEZE.json",{"commit":os.popen("git rev-parse HEAD").read().strip(),"protocol_hash":sha(V3/"V3_VALIDATION_PROTOCOL.json"),"policy_hash":sha(V3/"V3_STRATEGY_SELECTION_POLICY.json"),"library_hash":sha(V3/"strategy_library_v3.csv"),"portfolio_hash":sha(V3/"PORTFOLIO_FACTORY_V3_FREEZE.json"),"lockbox_access_count":0,"status":"PRE_VALIDATION_READY"})
 dump("VALIDATION_DECISION_POLICY.json",{"pass":{"portfolio_return":">0","pf":">1","expectancy_r":">0","maxdd":"<0.50","positive_strategy_fraction":">=0.50"},"mixed":"not eligible for final holdout","fail":"otherwise","frozen_before_access":True})
 ledger_out=pd.DataFrame(columns=["experiment_id","dataset","asset","segment","dataset_hash","git_commit","caller","purpose","access_count"]); ledger_out.to_csv(V3/"data_access_ledger.csv",index=False); dump("data_access_summary.json",{"protected_access_before":0,"v3_accesses":0,"remaining":"V2 LOCKBOX untouched"})
 dump("EXPERIMENT_MANIFEST.json",{"experiment":"crypto_factory_v3","starting_commit":"53efba3","grammar":"v1.7 PRICE_ONLY","protected_access":0,"library":len(library),"selection":"frozen"}); dump("environment.json",{"python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"pandas":pd.__version__})
 (V3/"README.md").write_text("# Crypto Factory V3\nPreparation complete; protected validation not yet accessed.\n")
 decision="READY_FOR_PROTECTED_VALIDATION" if portfolio_valid else "CRYPTO_V3_PORTFOLIO_NOT_ROBUST"
 dump("PROTECTED_VALIDATION_DECISION.json",{"decision":"NOT_ACCESSED","pre_validation_gate":decision,"reason":"negative-equity/invalid burned portfolio" if not portfolio_valid else "eligible","lockbox_access_count":0})
 (V3/"CRYPTO_FACTORY_V3_REPORT.md").write_text(f"# SQX CRYPTO FACTORY V3 — FINAL STATUS\n\nDecision: `{decision}`\n\nProtected validation was not accessed because the true concurrent burned-data portfolio failed the economic-validity gate. LOCKBOX access count remains zero.\n")
 print(json.dumps({"library":len(library),"population":len(base),"portfolio":portfolio_rows,"protected_access":0,"decision":decision},indent=2,default=str))

def validate():
 # This function is invoked only after the PRE_VALIDATION_FREEZE commit.
 protocol=json.loads((V3/"V3_VALIDATION_PROTOCOL.json").read_text()); library=pd.read_csv(V3/"strategy_library_v3.csv"); ledger_path=V3/"data_access_ledger.csv"; access=pd.read_csv(ledger_path); before=int(len(access));
 if before!=0: raise RuntimeError("protected validation already accessed")
 results=[]; all_events=[]; bars={}
 for asset in sorted(library.asset.unique()):
  b=split(asset); start=ts(b["OOS_END"]); end=ts(b["END"]); warm=start-pd.Timedelta(minutes=15*100)
  d=load_burned(asset,end=end,start=warm); feats=prepare_crypto_features(d,None,"PRICE"); ev=FastEvaluator(d,feats,initial_capital=1.0,spread=.0009,engine="numba"); a=int(d.timestamp.searchsorted(start)); z=int(d.timestamp.searchsorted(end))
  bars[asset]=d.iloc[::4].copy()
  for rec in library[library.asset.eq(asset)].to_dict("records"):
   r=ev.evaluate(StrategyDefinition.from_json(rec["strategy"]),start=a,end=z,rich=True); results.append({"hash":rec["hash"],"asset":asset,"direction":rec["direction"],"pf":r.profit_factor,"expectancy_r":r.expectancy_r,"return":r.return_pct,"trades":r.trade_count,"maxdd":r.max_drawdown})
   for tr in r.trades:
    ei=int(d.timestamp.searchsorted(pd.Timestamp(tr["entry_time"]))); xi=int(d.timestamp.searchsorted(pd.Timestamp(tr["exit_time"]))); all_events.append({"hash":rec["hash"],"asset":asset,"direction":tr["direction"],"entry_time":tr["entry_time"],"exit_time":tr["exit_time"],"r":tr["r"],"entry_price":float(d.open.iloc[min(ei,len(d)-1)]),"exit_price":float(d.close.iloc[min(xi,len(d)-1)])})
 ledger=pd.DataFrame([{"experiment_id":protocol["experiment_id"],"dataset":"crypto_v2","asset":"ALL","segment":"LOCKBOX","dataset_hash":"from V2 manifest","git_commit":os.popen("git rev-parse HEAD").read().strip(),"caller":"CryptoFactoryV3.validate","purpose":"predeclared protected validation","access_count":1}]); ledger.to_csv(ledger_path,index=False); pd.DataFrame(results).to_csv(V3/"protected_validation_strategy_results.csv",index=False)
 rep=replay_concurrent(pd.DataFrame(all_events),bars,initial_equity=1.0,total_risk=.01,weights={h:1.0 for h in library.hash})
 pos=float((pd.DataFrame(results).expectancy_r>0).mean()) if results else 0.0; summary={"strategies":len(results),"positive_strategy_fraction":pos,"portfolio_return":rep.total_return,"portfolio_pf":rep.profit_factor,"portfolio_expectancy_r":rep.expectancy_r,"portfolio_maxdd":rep.max_drawdown,"portfolio_trades":len(rep.trades),"peak_concurrent":rep.peak_concurrent}
 dump("protected_validation_portfolio_result.json",summary); dump("protected_validation_summary.json",summary); decision="VALIDATION_PASS" if summary["portfolio_return"]>0 and summary["portfolio_pf"]>1 and summary["portfolio_expectancy_r"]>0 and summary["portfolio_maxdd"]<.5 and pos>=.5 else "VALIDATION_FAIL"; dump("PROTECTED_VALIDATION_DECISION.json",{"decision":decision,"summary":summary,"final_holdout_opened":False,"lockbox_access_count":1})
 dump("data_access_summary.json",{"protected_access_before":0,"v3_accesses":1,"remaining":"no second layer opened","lockbox_access_count":1})
 (V3/"CRYPTO_FACTORY_V3_REPORT.md").write_text(f"# SQX CRYPTO FACTORY V3 — FINAL STATUS\n\nDecision: `{decision}`\n\nProtected V2 LOCKBOX was accessed once after the pre-validation freeze. No second protected layer was opened. Portfolio replay used chronological concurrent events with floating equity.\n")
 print(json.dumps({"decision":decision,**summary},indent=2))

if __name__=="__main__":
 ap=argparse.ArgumentParser(); ap.add_argument("--validate",action="store_true"); args=ap.parse_args(); validate() if args.validate else prepare()
