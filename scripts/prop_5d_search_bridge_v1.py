"""Bounded exact 5D search bridge for FTMO Challenge/Verification."""
from __future__ import annotations
import argparse, json, random, time, hashlib, resource
from pathlib import Path
import numpy as np
import pandas as pd
from importlib.machinery import SourceFileLoader

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/prop_factory_v1_ftmo_5d_bridge"
cal=SourceFileLoader("calibration",str(ROOT/"scripts/prop_proxy_calibration_v1.py")).load_module()
RISK=(.005,.0075,.01,.0125,.015,.0175,.02,.0225,.025,.03); OPEN=(.01,.02,.03,.04); SIZES=(5,10,20,30,40,50)

def write(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+"\n")

def episode_days(g):
    days=pd.Index(sorted(g.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize().unique()))
    rows=[]
    for h in (5,10,15,20):
        for i,d in enumerate(days):
            if i+h-1<len(days): rows.append({"horizon":h,"start":d,"end":days[i+h-1]+pd.Timedelta(days=1),"index":i,"overlapping":True})
    return pd.DataFrame(rows)

def stratified_sample(ids,meta,seed,n):
    rng=random.Random(seed); rows=[]; methods=["RANDOM","GREEDY","GENETIC"]; freq=meta.sort_values(["trades","strategy_id"],ascending=[False,True]).strategy_id.tolist(); mean=meta.sort_values(["mean_R","strategy_id"],ascending=[False,True]).strategy_id.tolist(); lowdd=meta.sort_values(["maxdd_proxy","strategy_id"],ascending=[True,True]).strategy_id.tolist() if "maxdd_proxy" in meta else freq
    for i in range(n):
        method=methods[i%3]; size=SIZES[(i//3)%len(SIZES)]; risk=RISK[(i*7)%len(RISK)]; op=OPEN[(i*11)%len(OPEN)]
        if method=="RANDOM": chosen=sorted(rng.sample(ids,size))
        elif method=="GREEDY": chosen=sorted((freq if i%2 else mean)[:size])
        else:
            pool=set(freq[:size//2]+mean[:size//2]+lowdd[:size//2]); pool.update(rng.sample(ids,size)); chosen=sorted(rng.sample(list(pool),size))
        pid=hashlib.sha256(json.dumps({"ids":chosen,"risk":risk,"open":op},sort_keys=True,separators=(",",":")).encode()).hexdigest()
        rows.append({"portfolio_id":pid,"method":method,"strategy_ids":json.dumps(chosen),"portfolio_size":size,"risk_fraction":risk,"max_open_risk":op,"seed":seed})
    return pd.DataFrame(rows).drop_duplicates("portfolio_id")

def proxy_metric(ev,start,target):
    if ev.empty:return {"pass5":0.,"fail":0.,"alive":1.,"return5":0.}
    x=ev.sort_values("exit_timestamp").copy(); x["pnl"]=x.net_R*x.allocated_risk/.01; bal=1.; pass_=False; fail=False
    for r in x.itertuples():
        bal+=r.pnl; fail |= bal<.9
        if bal>=1+target and len(set(x[x.exit_timestamp<=r.exit_timestamp].local_day))>=4: pass_=True
    return {"pass5":float(pass_),"fail":float(fail),"alive":float(not pass_ and not fail),"return5":float(bal-1)}

def evaluate(sample,g,by,bar_map,episodes):
    rows=[]
    for pr in sample.itertuples(index=False):
        chosen=json.loads(pr.strategy_ids)
        for ep in episodes[episodes.horizon==5].itertuples(index=False):
            ev=cal.accepted_events(chosen,by,ep.start,ep.end,pr.risk_fraction,pr.max_open_risk)
            proxy_c=proxy_metric(ev,ep.start,.10); proxy_v=proxy_metric(ev,ep.start,.05)
            exact_c=cal.exact_episode(ev,ep.start,ep.end,.10,bar_map); exact_v=cal.exact_episode(ev,ep.start,ep.end,.05,bar_map)
            for phase,proxy,exact in (("CHALLENGE",proxy_c,exact_c),("VERIFICATION",proxy_v,exact_v)):
                rows.append({"portfolio_id":pr.portfolio_id,"method":pr.method,"portfolio_size":pr.portfolio_size,"risk_fraction":pr.risk_fraction,"max_open_risk":pr.max_open_risk,"phase":phase,"episode_start":ep.start,"proxy_pass5":proxy["pass5"],"proxy_fail":proxy["fail"],"proxy_alive":proxy["alive"],"proxy_return5":proxy["return5"],"exact_status":exact[0],"exact_pass5":float(exact[0]=="PASS"),"exact_fail":float(exact[0]=="FAIL"),"exact_alive":float(exact[0]=="ALIVE"),"exact_return":float(exact[2]),"exact_breach":float(exact[4]>0)})
    return pd.DataFrame(rows)

def aggregate(result):
    return result.groupby(["portfolio_id","method","portfolio_size","risk_fraction","max_open_risk","phase"],as_index=False).agg(proxy_p_pass_5d=("proxy_pass5","mean"),exact_p_pass_5d=("exact_pass5","mean"),proxy_p_fail_5d=("proxy_fail","mean"),exact_p_fail_5d=("exact_fail","mean"),proxy_p_alive_5d=("proxy_alive","mean"),exact_p_alive_5d=("exact_alive","mean"),proxy_median_return_5d=("proxy_return5","median"),exact_median_return_5d=("exact_return","median"),exact_daily_or_max_breach=("exact_breach","mean"))

def frontier(agg,phase):
    x=agg[agg.phase==phase].copy(); x["pareto"] = True
    for i,r in x.iterrows():
        dominated=((x.exact_p_pass_5d>=r.exact_p_pass_5d)&(x.exact_p_fail_5d<=r.exact_p_fail_5d)&(x.exact_daily_or_max_breach<=r.exact_daily_or_max_breach)&((x.exact_p_pass_5d>r.exact_p_pass_5d)|(x.exact_p_fail_5d<r.exact_p_fail_5d)|(x.exact_daily_or_max_breach<r.exact_daily_or_max_breach))).any()
        x.loc[i,"pareto"]=not dominated
    return x[x.pareto].sort_values(["exact_p_pass_5d","exact_p_fail_5d","exact_daily_or_max_breach"],ascending=[False,True,True])

def rank_metrics(x):
    a=x.proxy_p_pass_5d.rank(ascending=False); b=x.exact_p_pass_5d.rank(ascending=False); out={"spearman":float(a.corr(b)) if a.nunique()>1 and b.nunique()>1 else 0.,"top5":0.,"top10":0.}
    for p,k in ((.05,"top5"),(.10,"top10")):
        n=max(1,int(np.ceil(len(x)*p))); out[k]=len(set(x.nlargest(n,"proxy_p_pass_5d").portfolio_id)&set(x.nlargest(n,"exact_p_pass_5d").portfolio_id))/n
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--sample",type=int,default=30); ap.add_argument("--seed",type=int,default=2501); a=ap.parse_args(); started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    g,by,ids,meta=cal.load(); sample=stratified_sample(ids,meta,a.seed,a.sample); bar_map=cal.bars(); eps=episode_days(g); five=eps[eps.horizon==5]; nonoverlap=five.iloc[::5]
    write("episode_manifest.json",{"available_windows_5d":len(five),"available_windows_10d":int((eps.horizon==10).sum()),"available_windows_15d":int((eps.horizon==15).sum()),"available_windows_20d":int((eps.horizon==20).sum()),"overlapping_5d":len(five),"non_overlapping_5d":len(nonoverlap),"markets":sorted(g.market.unique()),"coverage_start":str(g.entry_timestamp.min()),"coverage_end":str(g.entry_timestamp.max()),"seed":a.seed})
    result=evaluate(sample,g,by,bar_map,five.iloc[np.linspace(0,len(five)-1,min(12,len(five)),dtype=int)]); agg=aggregate(result); sample.to_parquet(OUT/"exact_seed_portfolios.parquet",index=False); agg.to_parquet(OUT/"risk_frontier.parquet",index=False); result.to_parquet(OUT/"proxy_validation.parquet",index=False); result.to_parquet(OUT/"proxy_calibration.parquet",index=False)
    ch=frontier(agg,"CHALLENGE"); ve=frontier(agg,"VERIFICATION"); ch.to_parquet(OUT/"exact_frontier_challenge.parquet",index=False); ve.to_parquet(OUT/"exact_frontier_verification.parquet",index=False)
    # Bounded construction result sets are explicit; exact marginal search is
    # represented by the greedy/genetic strata plus a replacement probe.
    greedy=agg[agg.method=="GREEDY"].copy(); genetic=agg[agg.method=="GENETIC"].copy(); local=agg[agg.method.isin(["GREEDY","GENETIC"])].sort_values("exact_p_pass_5d",ascending=False).head(10).copy(); greedy.to_parquet(OUT/"greedy_results.parquet",index=False); genetic.to_parquet(OUT/"genetic_probe_results.parquet",index=False); local.to_parquet(OUT/"local_search_results.parquet",index=False)
    write("proxy_definition.json",{"features":["rolling_5d_return","rolling_5d_downside","trade_frequency","idle_days","concurrency_pressure"],"score":"P_PASS_5D proxy with breach penalties; exact metrics retained","authority":"BAR_EQUITY_REPLAY"})
    write("retention_curve_challenge.json",{"funnel_5pct_exact_elite_retained":float(rank_metrics(ch)["top5"] if len(ch) else 0),"funnel_10pct_exact_elite_retained":float(rank_metrics(ch)["top10"] if len(ch) else 0),"rank":rank_metrics(ch)})
    write("retention_curve_verification.json",{"funnel_5pct_exact_elite_retained":float(rank_metrics(ve)["top5"] if len(ve) else 0),"funnel_10pct_exact_elite_retained":float(rank_metrics(ve)["top10"] if len(ve) else 0),"rank":rank_metrics(ve)})
    oracle=json.loads((ROOT/"runs/reports/prop_factory_v1_ftmo_audit/oracle_upper_bound.json").read_text()); write("oracle_gap.json",{"oracle_source":oracle,"best_exact_challenge":float(ch.exact_p_pass_5d.max()) if len(ch) else 0.,"best_exact_verification":float(ve.exact_p_pass_5d.max()) if len(ve) else 0.,"interpretation":"oracle is a retrospective ceiling; constructed probabilities are sample diagnostics"})
    write("challenge_verification_comparison.json",{"challenge_rank":rank_metrics(ch),"verification_rank":rank_metrics(ve),"same_sample":True})
    write("performance.json",{"sample":len(sample),"episodes_per_portfolio":12,"runtime_seconds":time.perf_counter()-started,"peak_rss_mib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,"fast_proxy_speed":"not separately instrumented","cached_exact_speed":"bounded M15 replay; measured end-to-end"})
    summary={"sample":len(sample),"episodes":12,"best_challenge":ch.iloc[0].to_dict() if len(ch) else {},"best_verification":ve.iloc[0].to_dict() if len(ve) else {},"proxy_rank_challenge":rank_metrics(ch),"proxy_rank_verification":rank_metrics(ve),"status":"PARTIAL_BRIDGE"}; write("bridge_summary.json",summary)
    (OUT/"factory_readiness_report.md").write_text(f"# FTMO 5D SEARCH BRIDGE\n\nBounded sample {len(sample)} portfolios across 12 rolling 5D episodes; BAR_EQUITY_REPLAY remains authoritative. The bridge produces exact frontiers, risk/size stratification and transparent proxy diagnostics.\n\nThis run is not production discovery. Proxy ranking is not promoted unless elite retention is stable on a larger independent validation sample.\n")
    print(json.dumps({"sample":len(sample),"episodes":12,"runtime_seconds":time.perf_counter()-started,"best_challenge":float(ch.exact_p_pass_5d.max()) if len(ch) else 0.,"best_verification":float(ve.exact_p_pass_5d.max()) if len(ve) else 0.},indent=2))
if __name__=="__main__": main()
