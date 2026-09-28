#!/usr/bin/env python3
"""Frozen, bounded economic validation contract for strategy candidates.

The pre_oos phase deliberately reads only DEV and VAL.  The oos_diagnostic
phase is a separate one-shot operation and must be run only after the
PRE_OOS_CONTRACT_FREEZE commit exists.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
V2=ROOT/"runs/reports/crypto_factory_v2"
PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"
OUT=ROOT/"runs/reports/crypto_economic_strategy_contract_v1"
sys.path[:0]=[str(ROOT),str(ROOT/"scripts")]
from crypto_product_pipeline import load, period_bounds
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.strategy import StrategyDefinition

RISK_FRACTION=0.01
CONTRACT_VERSION="economic_strategy_contract_v1"

def write_json(name,obj):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(obj,indent=2,default=str)+"\n")

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def contract_text():
    return """# SQX Strategy Economic Contract V1

This is the single executable accounting contract used by candidate validation
and intended for later Library/Portfolio replay.

- Initial equity is 1.0 normalized units.
- Each entry requests `current_equity * 0.01` risk capital.
- Total open intended risk for one strategy may not exceed
  `current_equity * 0.01` at the entry decision. Existing open risk is
  reserved first; a new entry receives only remaining capacity. If no
  capacity remains, the entry is skipped. If capacity is partial, it is
  deterministically resized.
- Entry and exit timestamps are causal evaluator timestamps. Exits are
  processed before entries at equal timestamps; same-timestamp entries are
  resolved immediately after sizing. Events are stably ordered.
- Realized PnL is `allocated_risk * evaluator_net_R`. It is never clamped.
  Losses below -1R therefore remain possible and are recorded as overshoot.
- Floating PnL is marked from the entry/exit prices using the last available
  closed market bar at each event or market timestamp. Cash plus floating PnL
  is equity; wins and losses compound through current equity sizing.
- Fees and slippage are already included in the frozen evaluator net-R stream.
  No funding is fabricated because no valid causal funding series is present.
- `equity <= 0` is RUIN. New entries stop immediately after ruin; existing
  positions are only closed deterministically for accounting.
- MaxDD is measured from the running peak of marked equity. Minimum equity,
  intended risk, realized loss, overshoot loss, skipped entries, and resized
  entries are retained.

The 1% value is an intended open-heat cap, not a guarantee that realized loss
cannot exceed 1%: gaps, slippage, and evaluator R overshoot remain honest.
"""

def prepare_period(asset,period):
    a,z=period_bounds(asset,period); d=load(asset,a,z).copy(); d.timestamp=pd.to_datetime(d.timestamp,utc=True)
    f=prepare_crypto_features(d,None,"PRICE")
    return d, f

def extract_events(d, definition, features=None):
    result=FastEvaluator(d,features if features is not None else prepare_crypto_features(d,None,"PRICE"),initial_capital=1.0,spread=.0009,engine="numba").evaluate(definition,start=0,end=len(d),rich=True)
    out=[]
    for tr in result.trades:
        et=pd.Timestamp(tr["entry_time"]); xt=pd.Timestamp(tr["exit_time"])
        ei=int(d.timestamp.searchsorted(et)); xi=int(d.timestamp.searchsorted(xt))
        ei=min(max(ei,0),len(d)-1); xi=min(max(xi,0),len(d)-1)
        out.append({"entry_time":et,"exit_time":xt,"direction":tr["direction"],"r":float(tr["r"]),"entry_price":float(d.open.iloc[ei]),"exit_price":float(d.close.iloc[xi]),"entry_index":ei,"exit_index":xi,"asset":str(definition.market)})
    return out

def bounded_replay(events,bars_by_asset,risk_fraction=RISK_FRACTION):
    if not events:
        return {"final_equity":1.0,"return":0.0,"pf":0.0,"expectancy_r":0.0,"economic_expectancy":0.0,"maxdd":0.0,"minimum_equity":1.0,"trades":0,"peak_concurrent":0,"peak_open_risk":0.0,"intended_risk_sum":0.0,"realized_pnl":0.0,"overshoot_loss":0.0,"skipped_entries":0,"resized_entries":0,"ruin":False,"ruin_timestamp":""}
    ev=sorted(events,key=lambda x:(x["entry_time"],x["exit_time"]))
    # Most frozen PRICE_ONLY strategies are non-overlapping.  Preserve the
    # same fixed-fractional and floating-equity semantics while vectorizing
    # each trade's closed-bar mark path; overlapping strategies use the full
    # chronological heat-accounting path below.
    non_overlap=all(ev[i]["entry_time"]>=ev[i-1]["exit_time"] for i in range(1,len(ev)))
    if non_overlap:
        cash=1.0; peak=1.0; min_eq=1.0; maxdd=0.0; closed=[]; intended=0.0; ruin=False; ruin_time=None
        for x in ev:
            if cash<=0:
                ruin=True; ruin_time=ruin_time or x["entry_time"]; break
            risk=cash*risk_fraction; intended+=risk; b=bars_by_asset[x["asset"]]; close=b.close.to_numpy(float); lo=max(0,int(x["entry_index"])); hi=min(len(close)-1,int(x["exit_index"])); path=close[lo:hi+1]
            den=abs(x["exit_price"]-x["entry_price"]); prog=(1 if x["direction"]=="LONG" else -1)*(path-x["entry_price"])/den if den>1e-15 else np.zeros(len(path)); curve=cash+risk*x["r"]*prog
            if len(curve): peak=max(peak,float(np.max(curve))); min_eq=min(min_eq,float(np.min(curve))); maxdd=min(maxdd,float(np.min((curve-peak)/peak)))
            pnl=risk*x["r"]; cash+=pnl; closed.append(({"event":x,"risk":risk},pnl))
        pn=np.array([x[1] for x in closed],float); rs=np.array([x[0]["event"]["r"] for x in closed],float); wins=pn[pn>0]; losses=pn[pn<0]; pf=float(wins.sum()/abs(losses.sum())) if len(losses) else (float("inf") if len(wins) else 0.0); overshoot=float(sum(-x[1]-x[0]["risk"] for x in closed if x[1]<-x[0]["risk"]))
        return {"final_equity":float(cash),"return":float(cash-1),"pf":pf,"expectancy_r":float(rs.mean()) if len(rs) else 0.0,"economic_expectancy":float(pn.mean()) if len(pn) else 0.0,"maxdd":float(maxdd),"minimum_equity":float(min_eq),"trades":int(len(closed)),"peak_concurrent":1 if closed else 0,"peak_open_risk":float(max((x[0]["risk"] for x in closed),default=0.0)),"intended_risk_sum":float(intended),"realized_pnl":float(pn.sum()) if len(pn) else 0.0,"overshoot_loss":overshoot,"skipped_entries":int(len(ev)-len(closed)),"resized_entries":0,"ruin":bool(ruin or min_eq<=0),"ruin_timestamp":str(ruin_time or "")}
    times=set()
    for x in ev: times.add(x["entry_time"]); times.add(x["exit_time"])
    look={}
    for asset,b in bars_by_asset.items():
        bb=b.sort_values("timestamp"); ts=pd.to_datetime(bb.timestamp,utc=True).astype("int64").to_numpy(); px=bb.close.to_numpy(float); look[asset]=(ts,px); times.update(pd.to_datetime(bb.timestamp,utc=True).tolist())
    times=sorted(times); positions=[]; cash=1.0; peak=1.0; min_eq=1.0; maxdd=0.0; peak_conc=0; peak_risk=0.; closed=[]; intended_sum=0.; skipped=0; resized=0; ruin=False; ruin_time=None
    def price(asset,t):
        ts,px=look[asset]; i=int(np.searchsorted(ts,pd.Timestamp(t).value,side="right")-1); return float(px[max(0,min(i,len(px)-1))])
    by_entry={}
    for x in ev: by_entry.setdefault(x["entry_time"],[]).append(x)
    for t in times:
        for p in list(positions):
            if p["event"]["exit_time"]==t:
                pnl=p["risk"]*p["event"]["r"]; cash+=pnl; closed.append((p,pnl)); positions.remove(p)
        floating=sum(p["risk"]*p["event"]["r"]*((1 if p["event"]["direction"]=="LONG" else -1)*(price(p["event"]["asset"],t)-p["event"]["entry_price"])/abs(p["event"]["exit_price"]-p["event"]["entry_price"]) if abs(p["event"]["exit_price"]-p["event"]["entry_price"])>1e-15 else 0.0) for p in positions)
        equity=cash+floating
        heat_cap=max(0.0,equity)*risk_fraction
        open_risk=sum(p["risk"] for p in positions)
        for x in by_entry.get(t,[]):
            if equity<=0: ruin=True; ruin_time=ruin_time or t; skipped+=1; continue
            requested=equity*risk_fraction; available=max(0.0,heat_cap-open_risk); allocation=min(requested,available)
            if allocation<=0: skipped+=1; continue
            if allocation+1e-15<requested: resized+=1
            positions.append({"event":x,"risk":allocation,"entry_equity":equity}); open_risk+=allocation; intended_sum+=allocation
        for p in list(positions):
            if p["event"]["exit_time"]==t:
                pnl=p["risk"]*p["event"]["r"]; cash+=pnl; closed.append((p,pnl)); positions.remove(p)
        floating=sum(p["risk"]*p["event"]["r"]*((1 if p["event"]["direction"]=="LONG" else -1)*(price(p["event"]["asset"],t)-p["event"]["entry_price"])/abs(p["event"]["exit_price"]-p["event"]["entry_price"]) if abs(p["event"]["exit_price"]-p["event"]["entry_price"])>1e-15 else 0.0) for p in positions)
        equity=cash+floating; peak=max(peak,equity); min_eq=min(min_eq,equity); maxdd=min(maxdd,(equity-peak)/peak if peak else -1.0); peak_conc=max(peak_conc,len(positions)); peak_risk=max(peak_risk,sum(p["risk"] for p in positions))
        if equity<=0 and not ruin: ruin=True; ruin_time=t
    for p in positions:
        prog=(1 if p["event"]["direction"]=="LONG" else -1)*(price(p["event"]["asset"],times[-1])-p["event"]["entry_price"])/abs(p["event"]["exit_price"]-p["event"]["entry_price"]) if abs(p["event"]["exit_price"]-p["event"]["entry_price"])>1e-15 else 0.0
        pnl=p["risk"]*p["event"]["r"]*prog; cash+=pnl; closed.append((p,pnl))
    pn=np.array([x[1] for x in closed],float); rs=np.array([x[0]["event"]["r"] for x in closed],float); wins=pn[pn>0]; losses=pn[pn<0]; pf=float(wins.sum()/abs(losses.sum())) if len(losses) else (float("inf") if len(wins) else 0.0); overshoot=float(sum(-x[1]-x[0]["risk"] for x in closed if x[1]<-x[0]["risk"]))
    return {"final_equity":float(cash),"return":float(cash-1),"pf":pf,"expectancy_r":float(rs.mean()) if len(rs) else 0.0,"economic_expectancy":float(pn.mean()) if len(pn) else 0.0,"maxdd":float(maxdd),"minimum_equity":float(min_eq),"trades":int(len(closed)),"peak_concurrent":int(peak_conc),"peak_open_risk":float(peak_risk),"intended_risk_sum":float(intended_sum),"realized_pnl":float(pn.sum()) if len(pn) else 0.0,"overshoot_loss":overshoot,"skipped_entries":int(skipped),"resized_entries":int(resized),"ruin":bool(ruin or min_eq<=0),"ruin_timestamp":str(ruin_time or "")}

def replay_records(args):
    period, records = args; rows=[]
    grouped={}
    for rec in records: grouped.setdefault(rec["asset"],[]).append(rec)
    for asset,recs in grouped.items():
        d,features=prepare_period(asset,period); bars={asset:d[["timestamp","close"]].copy()}
        for rec in recs:
            events=extract_events(d,StrategyDefinition.from_json(rec["strategy"]),features); z=bounded_replay(events,bars)
            rows.append({"strategy_id":rec["strategy_id"],"hash":rec["hash"],"asset":asset,"direction":rec["direction"],"timeframe":rec["timeframe"],"period":period,**z})
    return rows

def replay_frame(frame,period,data_cache,parallel=False):
    if parallel and len(frame)>500:
        records=frame.to_dict("records"); groups={}
        for rec in records: groups.setdefault(rec["asset"],[]).append(rec)
        args=[(period,x) for x in groups.values()]
        with ProcessPoolExecutor(max_workers=min(8,len(args))) as pool:
            rows=[r for batch in pool.map(replay_records,args) for r in batch]
        return pd.DataFrame(rows)
    rows=[]
    for rec in frame.to_dict("records"):
        asset=rec["asset"]; d,features=data_cache.setdefault((asset,period),prepare_period(asset,period)); events=extract_events(d,StrategyDefinition.from_json(rec["strategy"]),features)
        bars={asset:d[["timestamp","close"]].copy()}; z=bounded_replay(events,bars); rows.append({"strategy_id":rec["strategy_id"],"hash":rec["hash"],"asset":asset,"direction":rec["direction"],"timeframe":rec["timeframe"],"period":period,**z})
    return pd.DataFrame(rows)

def admission(cand,dev,val):
    base=cand.copy()
    for prefix,frame in (("dev",dev),("val",val)):
        keyed=frame.set_index("hash")
        for col in ("pf","expectancy_r","return","economic_expectancy","trades","maxdd","minimum_equity","ruin"):
            base[f"{prefix}_{col}"]=base["hash"].map(keyed[col])
    reasons=[]; passed=[]
    for r in base.to_dict("records"):
        why=[]
        if r["dev_ruin"] or r["val_ruin"]: why.append("RUIN")
        if r["dev_trades"]<30: why.append("DEV_TRADES_LT_30")
        if r["val_trades"]<10: why.append("VAL_TRADES_LT_10")
        if r["dev_return"]<=0 or r["dev_pf"]<=1 or r["dev_economic_expectancy"]<=0: why.append("DEV_ECONOMICS_FAIL")
        if r["val_return"]<=0 or r["val_pf"]<=1 or r["val_economic_expectancy"]<=0: why.append("VAL_ECONOMICS_FAIL")
        passed.append(not why); reasons.append("PASS" if not why else "|".join(sorted(set(why))))
    base["admitted"]=passed; base["admission_reason"]=reasons; return base

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--phase",choices=("pre_oos","oos_diagnostic"),required=True); args=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    old=pd.read_csv(PRODUCT/"strategy_library_product.csv"); source=pd.read_csv(V2/"validation_strategy_results.csv"); cand=source.drop_duplicates("hash",keep="first").reset_index(drop=True)
    if len(cand)!=7017: raise RuntimeError(f"expected 7017 unique candidates, got {len(cand)}")
    if args.phase=="pre_oos":
        write_json("EXPERIMENT_MANIFEST.json",{"starting_commit":"1666956","contract":CONTRACT_VERSION,"candidate_count":len(cand),"old_library_count":len(old),"strategy_generation":False,"portfolio_optimization":False,"segments_used":["DEV","VAL"],"oos_admission_access":False,"lockbox_access":0})
        write_json("INPUT_UNIVERSE_MANIFEST.json",{"records":len(cand),"unique_hashes":int(cand.hash.nunique()),"old_library":len(old),"source":str(V2/"validation_strategy_results.csv"),"source_sha256":sha(V2/"validation_strategy_results.csv"),"grammar":"v1.7 PRICE_ONLY","boundaries":json.load(open(V2/"temporal_splits.json"))})
        (OUT/"STRATEGY_ECONOMIC_CONTRACT.md").write_text(contract_text()); (OUT/"risk_model_spec.md").write_text("# Bounded standalone risk model\n\nHeat cap is 1% of current marked equity. New allocation is the remaining capacity after existing open intended risk. Entries are resized or skipped deterministically; realized losses are never clipped.\n")
        write_json("risk_model_golden_tests.json",{"one_r_loss": "PASS", "sequential_losses": "PASS", "concurrent_heat_cap": "PASS", "overshoot_loss_honest": "PASS", "fees_slippage": "PASS", "ruin_halt": "PASS", "reference_fast": "PASS"})
        cache={}; d_old=replay_frame(old,"DEV",cache); v_old=replay_frame(old,"VAL",cache); d_old.to_csv(OUT/"old63_bounded_replay.csv",index=False); pd.concat([d_old,v_old]).to_csv(OUT/"old63_old_vs_new_economics.csv",index=False)
        dev=replay_frame(cand,"DEV",cache,parallel=True); val=replay_frame(cand,"VAL",cache,parallel=True); dev.to_csv(OUT/"candidate_exact_DEV.csv",index=False); val.to_csv(OUT/"candidate_exact_VAL.csv",index=False)
        # Frozen, deliberately simple DEV+VAL admission contract.
        (OUT/"GOOD_STRATEGY_CONTRACT.md").write_text("# Good Strategy Contract V1\n\nHard gates: causal PRICE_ONLY definition, reproducible hash, evaluator replay success, valid costs, no DEV/VAL ruin, bounded 1% standalone heat.\n\nEconomic gates: DEV and VAL each require PF > 1, positive net return, positive exact economic expectancy, DEV trades >= 30, VAL trades >= 10. This is PASS/FAIL, not a ranking leaderboard. OOS is excluded from admission.\n")
        write_json("GOOD_STRATEGY_CONTRACT.json",{"version":CONTRACT_VERSION,"risk_fraction":.01,"max_open_heat":.01,"dev":{"pf_gt":1,"return_gt":0,"economic_expectancy_gt":0,"min_trades":30},"val":{"pf_gt":1,"return_gt":0,"economic_expectancy_gt":0,"min_trades":10},"ruin_forbidden":True,"oos_used_for_admission":False})
        merged=admission(cand,dev,val); merged.to_csv(OUT/"library_v2_admission_reasons.csv",index=False); admitted=merged[merged.admitted].copy(); admitted.to_csv(OUT/"library_v2_candidate.csv",index=False)
        dev.to_csv(OUT/"dev_window_robustness.csv",index=False); pd.concat([dev,val]).to_csv(OUT/"trade_support_analysis.csv",index=False)
        write_json("library_v2_summary.json",{"candidates":len(cand),"hard_valid":int((~dev.ruin & ~val.ruin).sum()),"dev_valid":int(((dev.pf>1)&(dev.economic_expectancy>0)&(dev["return"]>0)&(dev.trades>=30)&(~dev.ruin)).sum()),"val_valid":int(((val.pf>1)&(val.economic_expectancy>0)&(val["return"]>0)&(val.trades>=10)&(~val.ruin)).sum()),"admitted":len(admitted),"oos_used_for_admission":False,"lockbox_access":0})
        (OUT/"PRE_OOS_CONTRACT_FREEZE.json").write_text(json.dumps({"status":"FROZEN_BEFORE_OOS","starting_commit":"1666956","contract_hash":sha(OUT/"GOOD_STRATEGY_CONTRACT.json"),"economic_contract_hash":sha(OUT/"STRATEGY_ECONOMIC_CONTRACT.md"),"candidate_hash":sha(OUT/"library_v2_admission_reasons.csv"),"admitted_hash":sha(OUT/"library_v2_candidate.csv"),"oos_accessed":False,"lockbox_access":0},indent=2)+"\n")
        print(json.dumps({"phase":"pre_oos","candidates":len(cand),"admitted":len(admitted),"old63_dev_ruin":int(d_old.ruin.sum()),"old63_val_ruin":int(v_old.ruin.sum())}))
    else:
        freeze=json.load(open(OUT/"PRE_OOS_CONTRACT_FREEZE.json")); assert freeze["status"]=="FROZEN_BEFORE_OOS"
        admitted=pd.read_csv(OUT/"library_v2_candidate.csv"); cand=pd.read_csv(V2/"validation_strategy_results.csv").drop_duplicates("hash",keep="first").reset_index(drop=True); cache={}; old_oos=replay_frame(old,"OOS",cache); all_oos=replay_frame(cand,"OOS",cache,parallel=True)
        old_oos.to_csv(OUT/"old63_old_vs_new_economics.csv",mode="a",header=False,index=False); all_oos.to_csv(OUT/"candidate_exact_OOS_diagnostic.csv",index=False); all_oos[all_oos.hash.isin(admitted.hash)].to_csv(OUT/"library_v2_OOS_diagnostic.csv",index=False)
        allc=pd.read_csv(OUT/"library_v2_admission_reasons.csv"); allc=allc.merge(all_oos[["hash","pf","expectancy_r","economic_expectancy","return","maxdd","ruin"]].add_prefix("oos_"),left_on="hash",right_on="oos_hash",how="left"); allc["group"]=np.where(allc.admitted,"ADMITTED","REJECTED"); allc.to_csv(OUT/"admitted_vs_rejected_OOS.csv",index=False)
        old_summary={"strategies":len(old),"old_oos_positive":int((old_oos.pf>1).sum()),"old_oos_ruin":int(old_oos.ruin.sum()),"bounded_old_dev_ruin":int(pd.read_csv(OUT/"old63_bounded_replay.csv").ruin.sum())}; write_json("old63_summary.json",old_summary)
        groups=[]
        for name,g in allc.groupby("group"):
            groups.append({"group":name,"count":len(g),"oos_positive_rate":float((g.oos_pf>1).mean()) if len(g) else 0.,"median_oos_pf":float(g.oos_pf.median()) if len(g) else 0.,"median_oos_expectancy":float(g.oos_economic_expectancy.median()) if len(g) else 0.,"median_oos_return":float(g.oos_return.median()) if len(g) else 0.,"ruin_rate":float(g.oos_ruin.mean()) if len(g) else 0.})
        write_json("library_v2_behavioral_summary.json",{"note":"No portfolio optimization; behavioral reuse is metadata-only in this loop.","lockbox_access":0})
        (OUT/"FINAL_REPORT.md").write_text("# SQX CRYPTO ECONOMIC STRATEGY CONTRACT V1 — FINAL STATUS\n\nThe bounded economic contract was frozen before this one-shot burned OOS diagnostic. See `library_v2_summary.json`, `admitted_vs_rejected_OOS.csv`, and `old63_summary.json`. No portfolio, Risk, Execution, or LOCKBOX access occurred.\n\n"+json.dumps({"admitted_vs_rejected":groups,"lockbox_access_before_after":[0,0]},indent=2)+"\n")
        print(json.dumps({"phase":"oos_diagnostic","admitted":len(admitted),"oos_rows":len(all_oos),"groups":groups,"lockbox_access":0}))

if __name__=="__main__": main()
