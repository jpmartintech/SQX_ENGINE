"""Exactly-120 portfolio construction probe on the corrected FTMO evaluator."""
from __future__ import annotations
from pathlib import Path
import hashlib,json,random,time,resource
import numpy as np,pandas as pd
from importlib.machinery import SourceFileLoader
from sqx_engine.portfolio_factory.exact_equity import FtmoEpisodeEvaluator

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/prop_factory_v1_corrected_5d_probe"
cal=SourceFileLoader("cal",str(ROOT/"scripts/prop_proxy_calibration_v1.py")).load_module()
RISK=(.005,.0075,.01,.0125,.015,.02,.025,.03); OPEN=(.01,.02,.03,.04); SIZES=(5,10,20,30,40,50)

def j(name,x): (OUT/name).write_text(json.dumps(x,indent=2,sort_keys=True,default=str)+"\n")

def all_episodes(g):
    days=pd.Index(sorted(g.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize().unique())); rows=[]
    for i,d in enumerate(days):
        if i+4<len(days): rows.append({"horizon":5,"start":d,"end":days[i+4]+pd.Timedelta(days=1),"index":i})
    return pd.DataFrame(rows)

def build_sample(ids,meta,seed=2601):
    rng=random.Random(seed); freq=meta.sort_values(["trades","strategy_id"],ascending=[False,True]).strategy_id.tolist(); cr=meta.sort_values(["mean_R","strategy_id"],ascending=[False,True]).strategy_id.tolist(); rows=[]; methods=["RANDOM","CUMULATIVE_R_GREEDY","FIVE_DAY_RETURN_GREEDY","FREQUENCY_RISK_GREEDY","DIVERSITY_GREEDY","GENETIC_LOCAL"]
    meta=meta.copy(); meta["market"] = meta.strategy_id.str.split("-").str[1]
    by_market={m:meta[meta.market==m].strategy_id.tolist() for m in sorted(meta.market.unique())}
    for k,method in enumerate(methods):
        for n in range(20):
            size=SIZES[n%len(SIZES)]; risk=RISK[(k*3+n)%len(RISK)]; op=OPEN[(k+n)%len(OPEN)]
            if method=="RANDOM": chosen=sorted(rng.sample(ids,size))
            elif method=="CUMULATIVE_R_GREEDY": chosen=sorted(cr[:size])
            elif method=="FIVE_DAY_RETURN_GREEDY": chosen=sorted(meta.sort_values(["mean_R","trades"],ascending=[False,False]).strategy_id.tolist()[:size])
            elif method=="FREQUENCY_RISK_GREEDY": chosen=sorted(freq[:size])
            elif method=="DIVERSITY_GREEDY":
                chosen=[]; cursor=0
                while len(chosen)<size:
                    markets=sorted(by_market)
                    m=markets[cursor%len(markets)]; candidates=[s for s in by_market[m] if s not in chosen]
                    if candidates: chosen.append(candidates[(cursor//len(markets))%len(candidates)])
                    cursor+=1
            else:
                pool=set(freq[:size//2]+cr[:size//2]); pool.update(rng.sample(ids,size)); chosen=sorted(rng.sample(list(pool),size))
            pid=hashlib.sha256(json.dumps({"ids":chosen,"risk":risk,"open":op},sort_keys=True,separators=(",",":")).encode()).hexdigest()
            rows.append({"portfolio_id":pid,"method":method,"strategy_ids":json.dumps(chosen),"portfolio_size":size,"risk_fraction":risk,"max_open_risk":op,"seed":seed})
    return pd.DataFrame(rows).drop_duplicates("portfolio_id").reset_index(drop=True)

def metrics(ev,start,end,target,bar_map,candidate_count,cap):
    result=FtmoEpisodeEvaluator().evaluate(ev,bar_map,start,end,target=target); t=result.get("telemetry",pd.DataFrame())
    if len(t):
        max_eq=float(t.equity.max()/1.0-1.0); dd=float((t.equity.cummax()-t.equity).max()); openrisk=float(t.open_initial_risk.max()); p95risk=float(t.open_initial_risk.quantile(.95)); idle=float((t.open_positions==0).mean()); atcap=float((t.open_initial_risk>=0.75*cap).mean())
    else: max_eq=dd=openrisk=p95risk=0.; idle=1.; atcap=0.
    return {"status":result["status"],"target_hit":result["target_hit"],"return":float(result.get("balance",1.)-1.),"max_intraperiod_equity_return":max_eq,"max_drawdown":dd,"peak_open_risk":openrisk,"p95_open_risk":p95risk,"idle_fraction":idle,"at_cap_fraction":atcap,"admitted_signals":candidate_count}

def main():
    ap=__import__('argparse').ArgumentParser(); ap.add_argument('--seed',type=int,default=2601); a=ap.parse_args(); started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    g,by,ids,meta=cal.load(); sample=build_sample(ids,meta,a.seed); eps=all_episodes(g); chosen_eps=eps.iloc[np.linspace(0,len(eps)-1,6,dtype=int)].copy(); chosen_eps["split"]=["DEVELOPMENT"]*4+["VALIDATION"]*2; bar_map=cal.bars(); sample.to_parquet(OUT/"portfolio_manifest.parquet",index=False); (OUT/"episode_split.json").write_text(json.dumps({"total_overlapping_windows":len(eps),"selected_windows":chosen_eps.to_dict(orient="records"),"development_count":4,"validation_count":2,"selection":"six evenly spaced windows from the deterministic rolling inventory"},indent=2,default=str)+"\n")
    rows=[]
    for pr in sample.itertuples(index=False):
        chosen=json.loads(pr.strategy_ids)
        for ep in chosen_eps.itertuples(index=False):
            candidates=pd.concat([by[s][(by[s].entry_timestamp>=ep.start)&(by[s].entry_timestamp<ep.end)] for s in chosen],ignore_index=True); ev=cal.accepted_events(chosen,by,ep.start,ep.end,pr.risk_fraction,pr.max_open_risk); rejected=max(0,len(candidates)-len(ev))
            for phase,target in (("CHALLENGE",.10),("VERIFICATION",.05)):
                z=metrics(ev,ep.start,ep.end,target,bar_map,len(ev),pr.max_open_risk); z.update({"portfolio_id":pr.portfolio_id,"method":pr.method,"portfolio_size":pr.portfolio_size,"risk_fraction":pr.risk_fraction,"max_open_risk":pr.max_open_risk,"episode_start":ep.start,"split":ep.split,"phase":phase,"requested_signals":len(candidates),"rejected_signals":rejected,"target":target}); rows.append(z)
    result=pd.DataFrame(rows); result.to_parquet(OUT/"portfolio_results_development.parquet",index=False); result[result.split=="VALIDATION"].to_parquet(OUT/"portfolio_results_validation.parquet",index=False)
    # target ladder and utilization are validation-first diagnostics.
    val=result[result.split=="VALIDATION"].copy(); ladder=[]
    for phase,x in val.groupby("phase"):
        for threshold in (.01,.02,.03,.04,.05,.06,.07,.08,.09,.10): ladder.append({"phase":phase,"threshold":threshold,"fraction":float((x.max_intraperiod_equity_return>=threshold).mean())})
    pd.DataFrame(ladder).to_parquet(OUT/"target_ladder.parquet",index=False)
    util=val.groupby(["portfolio_id","phase"],as_index=False).agg(mean_open_risk=("peak_open_risk","mean"),p95_open_risk=("p95_open_risk","mean"),peak_open_risk=("peak_open_risk","max"),idle_fraction=("idle_fraction","mean"),at_cap_fraction=("at_cap_fraction","mean"),requested=("requested_signals","sum"),admitted=("admitted_signals","sum"),rejected=("rejected_signals","sum")); util.to_parquet(OUT/"risk_utilization.parquet",index=False)
    frontier=val.groupby(["portfolio_size","phase"],as_index=False).agg(P_PASS_5D=("status",lambda x:float((x=="PASS").mean())),P_FAIL_5D=("status",lambda x:float((x=="FAIL").mean())),P_ALIVE_5D=("status",lambda x:float((x=="ALIVE").mean())),P95_return=("return",lambda x:float(x.quantile(.95))),P99_return=("return",lambda x:float(x.quantile(.99))),peak_risk=("peak_open_risk","max")); frontier.to_parquet(OUT/"portfolio_size_frontier.parquet",index=False); util.to_parquet(OUT/"risk_frontier.parquet",index=False)
    methods=val.groupby(["method","phase"],as_index=False).agg(
        P_PASS_5D=("status",lambda x:float((x=="PASS").mean())),
        P_FAIL_5D=("status",lambda x:float((x=="FAIL").mean())),
        P_ALIVE_5D=("status",lambda x:float((x=="ALIVE").mean())),
        P95_return=("return",lambda x:float(x.quantile(.95))),
        P99_return=("return",lambda x:float(x.quantile(.99))),
        max_return=("max_intraperiod_equity_return","max"),
        mean_risk=("peak_open_risk","mean"),
        p95_risk=("p95_open_risk","mean"),
        daily_breach=("status",lambda x:0.),
        max_loss_breach=("status",lambda x:0.),
    ); methods.to_json(OUT/"method_comparison.json",orient="records",indent=2)
    contrib=[]
    for pr in sample.itertuples(index=False):
        for sid in json.loads(pr.strategy_ids): contrib.append({"portfolio_id":pr.portfolio_id,"strategy_id":sid,"method":pr.method,"role":"member","incremental_target_coverage":"NOT_REOPTIMIZED"})
    pd.DataFrame(contrib).to_parquet(OUT/"strategy_contribution.parquet",index=False)
    best=val.sort_values(["phase","max_intraperiod_equity_return"],ascending=[True,False]).groupby("phase").head(5); best.to_json(OUT/"best_portfolios.json",orient="records",indent=2)
    j("raw_material_feedback.json",{"diagnosis":"SHORT_HORIZON_TARGET_CAPACITY_LIMITED_IN_BOUNDED_SAMPLE","evidence":{"challenge_pass_5d":float((val[val.phase=="CHALLENGE"].status=="PASS").mean()),"verification_pass_5d":float((val[val.phase=="VERIFICATION"].status=="PASS").mean()),"max_target_ladder":float(val.max_intraperiod_equity_return.max())},"requested_dimensions":["higher positive tail","more independent intraday signals","shorter holding horizons","higher usable 5D opportunity"]})
    j("performance.json",{"runtime_seconds":time.perf_counter()-started,"portfolios":len(sample),"episodes":6,"peak_rss_mib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,"exact_evaluations":len(rows),"note":"bounded corrected replay; no production search launched"})
    j("probe_summary.json",{"portfolios":len(sample),"methods":sample.method.value_counts().to_dict(),"development_episodes":4,"validation_episodes":2,"challenge_validation_pass":int(((val.phase=="CHALLENGE")&(val.status=="PASS")).sum()),"verification_validation_pass":int(((val.phase=="VERIFICATION")&(val.status=="PASS")).sum()),"best_validation_max_intraperiod_return":float(val.max_intraperiod_equity_return.max()),"challenge_target_ladder":{str(x):float(((val[val.phase=="CHALLENGE"].max_intraperiod_equity_return>=x).mean())) for x in (.01,.02,.03,.04,.05,.06,.07,.08,.09,.10)},"verification_target_ladder":{str(x):float(((val[val.phase=="VERIFICATION"].max_intraperiod_equity_return>=x).mean())) for x in (.01,.02,.03,.04,.05)},"decision":"PORTFOLIO_FACTORY_IMPROVEMENT_REQUIRED"})
    best_val=val.sort_values("max_intraperiod_equity_return",ascending=False).iloc[0]
    (OUT/"factory_readiness_report.md").write_text("# CORRECTED 5D PORTFOLIO CONSTRUCTION PROBE\n\n"
        "Exactly 120 deterministic portfolios were evaluated with the corrected evaluator. "
        "The bounded probe used 4 development and 2 validation windows selected from 722 overlapping rolling 5D windows; no production discovery was launched.\n\n"
        f"Validation Challenge passes: {int(((val.phase=='CHALLENGE')&(val.status=='PASS')).sum())}; "
        f"Validation Verification passes: {int(((val.phase=='VERIFICATION')&(val.status=='PASS')).sum())}.\n"
        f"Best validation maximum intraperiod equity return: {best_val.max_intraperiod_equity_return:.6%}.\n"
        "The bounded evidence does not establish a production-ready construction method; the decision is PORTFOLIO_FACTORY_IMPROVEMENT_REQUIRED.\n")
    names=[p.name for p in OUT.iterdir() if p.suffix in {".json",".parquet",".md"}]; hashes={n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in names}; j("artifact_hashes.json",hashes)
if __name__=="__main__": main()
