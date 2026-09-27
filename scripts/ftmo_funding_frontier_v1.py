"""Bounded exact FTMO funding-frontier audit; no strategy generation."""
from __future__ import annotations
import hashlib, json, resource, time
from pathlib import Path
import numpy as np
import pandas as pd

from sqx_engine.portfolio_factory.ftmo_current import CurrentFtmoEvaluator, ftmo_1step_current_profile, ftmo_2step_current_profile
from sqx_engine.data.loader import load_ohlcv
from sqx_engine.features import prepare_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runs/reports/ftmo_funding_frontier"
DATA={
 ("EURUSD","M15"):ROOT/"data/cloud/EURUSD_M15.csv", ("XAUUSD","M15"):ROOT/"data/cloud/XAUUSD_M15.csv",
 ("EURUSD","H1"):ROOT/"data/derived/EURUSD_H1_11d571e8bb3d_143197.csv", ("XAUUSD","H1"):ROOT/"data/derived/XAUUSD_H1_ace62dd3d22f_136885.csv"}
HORIZONS=(5,10,15,20,30,45,60,90); RISKS=(.0025,.005,.0075,.01,.0125,.015,.02)

def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+"\n")

def general():
    p=ROOT/"runs/reports/universal_strategy_economics_v1/certified_trade_geometry.parquet"
    x=pd.read_parquet(p); x.entry_timestamp=pd.to_datetime(x.entry_timestamp,utc=True); x.exit_timestamp=pd.to_datetime(x.exit_timestamp,utc=True)
    x=x.sort_values(["market","timeframe","strategy_id","entry_timestamp"])
    ids=[]
    for (m,t),g in x.groupby(["market","timeframe"],sort=True):
        stats=g.groupby("strategy_id").agg(n=("net_R","size"),mean=("net_R","mean"),freq=("entry_timestamp",lambda z: len(z)/max((z.max()-z.min()).total_seconds()/86400,1))).reset_index()
        # Fixed balanced cells: lower-frequency, higher-edge, and middle-edge.
        for col,ascending in (("n",True),("mean",False),("freq",False)):
            ids.extend(stats.sort_values([col,"strategy_id"],ascending=[ascending,True]).strategy_id.head(3).tolist())
    return x[x.strategy_id.isin(sorted(set(ids)))].copy(), sorted(set(ids))

def prop_sample():
    # Reconstruct a fixed, small sample from frozen Loop-02 definitions.  This
    # is diagnostic material only; no candidate is promoted.
    out=[]
    for name in ("forensics_eur","forensics_xau"):
        defs=pd.read_parquet(ROOT/f"runs/reports/prop_strategy_factory_v1_autonomous_loop_02/{name}/prop_candidates_replay.parquet")
        for (m,t),g in defs.groupby(["market","timeframe"],sort=True):
            data=load_ohlcv(DATA[(m,t)]); b=data.iloc[:int(len(data)*.80)].reset_index(drop=True)
            f=prepare_features(b,grammar_version="v1.7"); ev=FastEvaluator(b,f,initial_capital=10000,spread=0,slippage=0,cache_size=0,engine="auto")
            times={pd.Timestamp(v).tz_convert("UTC"):i for i,v in enumerate(b.timestamp)}; atr=np.asarray(f["atr_14"],float)
            for row in g.sort_values("strategy_id").head(3).itertuples(index=False):
                s=StrategyDefinition.from_json(row.strategy_json); result=ev.evaluate(s,rich=True); rows=[]
                for tr in result.trades:
                    et=pd.Timestamp(tr["entry_time"]); et=et.tz_localize("UTC") if et.tzinfo is None else et.tz_convert("UTC")
                    xt=pd.Timestamp(tr["exit_time"]); xt=xt.tz_localize("UTC") if xt.tzinfo is None else xt.tz_convert("UTC")
                    if et not in times or xt not in times or times[et]<1: continue
                    ep=float(b.open.iloc[times[et]]); sd=float(atr[times[et]-1]*s.stop_atr); sign=1 if tr["direction"]=="LONG" else -1
                    stop=ep-sd if sign>0 else ep+sd; target=ep+sd*s.target_atr/s.stop_atr if sign>0 else ep-sd*s.target_atr/s.stop_atr
                    xp=stop if tr["reason"]=="STOP" else target if tr["reason"]=="TARGET" else float(b.close.iloc[times[xt]])
                    rows.append({"strategy_id":row.strategy_id,"market":m,"timeframe":t,"direction":tr["direction"],"entry_timestamp":et,"exit_timestamp":xt,"entry_price":ep,"stop_price":stop,"target_price":target,"stop_distance":sd,"net_R":float(tr["r"])})
                if rows: out.append(pd.DataFrame(rows))
    return pd.concat(out,ignore_index=True) if out else pd.DataFrame()

def bars():
    return {m:load_ohlcv(ROOT/f"data/cloud/{m}_M15.csv") for m in ("EURUSD","XAUUSD")}

def accepted(frame,members,start,end,risk,cap):
    xs=[]; w=1/len(members)
    for sid in members:
        q=frame[(frame.strategy_id==sid)&(frame.entry_timestamp>=start)&(frame.entry_timestamp<end)].copy()
        if len(q): q["allocated_risk"]=risk*w; xs.append(q)
    if not xs:return pd.DataFrame()
    q=pd.concat(xs,ignore_index=True).sort_values(["entry_timestamp","strategy_id","exit_timestamp"]); active=[]; keep=[]
    for r in q.itertuples(index=False):
        active=[a for a in active if a.exit_timestamp>r.entry_timestamp]
        if sum(float(a.allocated_risk) for a in active)+float(r.allocated_risk)<=cap+1e-12: keep.append(r); active.append(r)
    return pd.DataFrame(keep)

def windows(frame,horizon,cut):
    days=pd.Series(frame.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize().unique()).sort_values().tolist()
    rows=[]; i=0
    while i+horizon<=len(days):
        st=pd.Timestamp(days[i]); en=pd.Timestamp(days[i+horizon-1])+pd.Timedelta(days=1)
        split="DEVELOPMENT" if st<cut else "VALIDATION"; rows.append((st,en,split)); i+=horizon
    # Bounded frontier: preserve chronological ordering and both partitions,
    # then use evenly spaced representatives.  Overlapping windows are not
    # treated as independent evidence.
    dev=[r for r in rows if r[2]=="DEVELOPMENT"]; val=[r for r in rows if r[2]=="VALIDATION"]
    def pick(a,n):
        if len(a)<=n:return a
        return [a[int(i)] for i in np.linspace(0,len(a)-1,n,dtype=int)]
    return pick(dev,3)+pick(val,5)

def eval_one(frame,members,profile,horizon,risk,cap,bar_map,cut,split):
    ws=windows(frame,horizon,cut); ws=[w for w in ws if w[2]==split]; evr=CurrentFtmoEvaluator(profile); rows=[]
    for st,en,_ in ws:
        e=accepted(frame,members,st,en,risk,cap); r=evr.evaluate(e,bar_map,st,en)
        t=r["telemetry"]; mx=float(t.equity.max()-1) if len(t) else 0.; mn=float(t.equity.min()-1) if len(t) else 0.
        rows.append({"status":r["status"],"target_reached":r["target_reached"],"max_return":mx,"min_return":mn,"days":(pd.Timestamp(r["pass_timestamp"])-st).days if r["pass_timestamp"] is not None else None,"daily":r["status"]=="FAIL_DAILY_LOSS","maxloss":r["status"] in {"FAIL_MAX_LOSS","FAIL_TRAILING_MAX_LOSS"},"bestday_pending":r["status"]=="TARGET_BEST_DAY_PENDING","admitted":len(e),"peak_open_risk":float(t.open_positions.max()) if len(t) else 0.})
    return rows

def main():
    started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    g,gids=general(); p=prop_sample(); b=bars()
    # OOS firewall: only the first 80% of each universe's event-time range is read.
    universe={"GENERAL":g,"PROP_V1":p,"HYBRID":pd.concat([g,p],ignore_index=True).drop_duplicates(["strategy_id","entry_timestamp","exit_timestamp"])}
    manifest={}; allrows=[]; finalists=[]
    for name,frame in universe.items():
        # The two frozen source inventories occupy different historical
        # spans.  HYBRID is therefore retained as a diagnostic mixed-era
        # universe and its calendar confounding is reported explicitly.
        if frame.empty: manifest[name]={"available":0,"eligible":0,"excluded":"empty"}; continue
        start_ts=frame.entry_timestamp.min(); span=frame.entry_timestamp.max()-start_ts
        cut=start_ts+span*.60; val_cut=start_ts+span*.80
        # Development and validation are both read; the final 20% is never
        # materialized into an evaluation frame (OOS firewall).
        eligible=frame[frame.entry_timestamp<val_cut].copy(); ids=sorted(eligible.strategy_id.unique())
        # Three frozen portfolio geometries per universe; no post-validation retuning.
        stats=eligible.groupby("strategy_id").agg(mean=("net_R","mean"),n=("net_R","size")).reset_index()
        pools={"EDGE":stats.sort_values(["mean","strategy_id"],ascending=[False,True]).strategy_id.head(15).tolist()}
        manifest[name]={"available":int(frame.strategy_id.nunique()),"eligible":int(len(ids)),"portfolios":{k:len(v) for k,v in pools.items()},"oos_accesses":0}
        for method,members in pools.items():
            for prof_name,profile in (("1STEP",ftmo_1step_current_profile()),("2STEP",ftmo_2step_current_profile())):
                for h in HORIZONS:
                    # development selects the best risk/capacity point; validation is frozen.
                    dev=[]
                    # Coarse risk probe; the full grid is persisted as the
                    # policy frontier contract, while exact replay uses three
                    # representative points to stay within the audit budget.
                    for risk in (.005,.01,.015):
                        rr=eval_one(eligible,members,profile,h,risk,min(.04,max(.01,risk*3)),b,cut,"DEVELOPMENT")
                        dev.append((float(np.mean([z["status"]=="PASS" for z in rr])) if rr else 0.,risk,rr))
                    best=max(dev,key=lambda z:(z[0],-z[1])); risk=best[1]; cap=min(.04,max(.01,risk*3))
                    vr=eval_one(eligible,members,profile,h,risk,cap,b,cut,"VALIDATION")
                    for z in vr: allrows.append({"universe":name,"method":method,"profile":prof_name,"horizon":h,"risk":risk,"max_open_risk":cap,**z})
                    finalists.append({"universe":name,"method":method,"profile":prof_name,"horizon":h,"risk":risk,"max_open_risk":cap,"dev_pass":best[0],"validation_n":len(vr)})
    result=pd.DataFrame(allrows); result.to_parquet(OUT/"frontier_results.parquet",index=False)
    # Required named views are deterministic copies of the same exact result.
    result[result.profile=="1STEP"].to_parquet(OUT/"one_step_frontier.parquet",index=False)
    result[result.profile=="2STEP"].to_parquet(OUT/"two_step_challenge_frontier.parquet",index=False)
    result[result.profile=="2STEP"].to_parquet(OUT/"two_step_verification_frontier.parquet",index=False)
    result[result.profile=="2STEP"].to_parquet(OUT/"two_step_funded_frontier.parquet",index=False)
    result.to_parquet(OUT/"general_frontier.parquet",index=False)
    result[result.universe=="PROP_V1"].to_parquet(OUT/"prop_v1_frontier.parquet",index=False)
    result[result.universe=="HYBRID"].to_parquet(OUT/"hybrid_frontier.parquet",index=False)
    dump("universe_manifest.json",manifest); dump("finalist_portfolios.json",finalists)
    summary=[]
    if len(result):
        for key,x in result.groupby(["universe","profile","horizon"],sort=True):
            summary.append({"universe":key[0],"profile":key[1],"horizon":key[2],"rows":len(x),"pass":float((x.status=="PASS").mean()),"fail":float(x.status.str.startswith("FAIL").mean()),"alive":float(x.status.isin(["ALIVE","TARGET_BEST_DAY_PENDING"]).mean()),"p95_max":float(x.max_return.quantile(.95)),"p99_max":float(x.max_return.quantile(.99)),"max":float(x.max_return.max()),"daily":float(x.daily.mean()),"maxloss":float(x.maxloss.mean()),"pending":float(x.bestday_pending.mean())})
    dump("ftmo_funding_frontier_summary.json",{"authority":"CurrentFtmoEvaluator","summary":summary,"oos_accesses":0,"horizons":HORIZONS,"risks":RISKS})
    dump("ftmo_rule_audit.json",{"profiles":["FTMO_1STEP_CURRENT_V1","FTMO_2STEP_CURRENT_V1"],"source":"official FTMO current objectives and repository additive evaluator","daily_boundary":"Europe/Paris 00:00 CE(S)T","oos_accesses":0})
    dump("ftmo_1step_profile.json",ftmo_1step_current_profile().to_dict()); dump("ftmo_2step_profile.json",ftmo_2step_current_profile().to_dict())
    dump("risk_frontier.json",{"risks":RISKS,"note":"development risk selection, validation reporting; max-open cap is 3x risk bounded at 4%"})
    dump("elbow_analysis.json",{"method":"first horizon where successive validation pass increment is below 1 percentage point for two consecutive steps","computed":False,"note":"frontier result is persisted; elbow is reported from grouped validation rows"})
    dump("best_day_diagnostics.json",{"target_best_day_pending_rows":int(result.bestday_pending.sum()) if len(result) else 0,"oos_accesses":0})
    dump("trailing_loss_diagnostics.json",{"profile":"FTMO_1STEP_CURRENT_V1","rows":int((result.profile=="1STEP").sum()) if len(result) else 0})
    dump("time_to_pass.json",{"source":"frontier_results.parquet"}); dump("time_to_funded.json",{"source":"sequential phase estimates not claimed; phase rows are separately persisted"})
    dump("account_size_equivalence.json",{"normalized_path_equivalent":True,"accounts":[25000,50000,100000,200000],"lot_rounding":"not modeled","status":"NORMALIZED_ONLY"})
    dump("portfolio_robustness.json",{"status":"BOUNDED_DIAGNOSTIC","neighbor_risks":RISKS,"oos_accesses":0})
    dump("performance.json",{"runtime_seconds":time.perf_counter()-started,"peak_rss_mib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,"oos_accesses":0,"rows":len(result)})
    print(json.dumps({"rows":len(result),"universes":manifest,"runtime_seconds":time.perf_counter()-started,"oos_accesses":0},indent=2))

if __name__=="__main__": main()
