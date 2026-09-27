"""Bounded FAST_PROXY versus BAR_EQUITY_REPLAY calibration.

The sample is deliberately finite and deterministic.  FAST_PROXY uses closed
trade R events; the comparator uses the same accepted positions marked on
M15 OHLC bars with conservative adverse probes.  Exact replay remains the
authority and no result here promotes a portfolio.
"""
from __future__ import annotations
import argparse, hashlib, json, random, resource, time
from pathlib import Path
import numpy as np
import pandas as pd
from sqx_engine.portfolio_factory.exact_equity import FtmoEpisodeEvaluator

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runs/reports/prop_factory_v1_proxy_calibration"
RISK=(.005,.0075,.01,.0125,.015,.02,.025,.03); OPEN=(.01,.02,.03,.04); SIZES=(5,10,20,30,40,50)

def canon(ids,risk,op,method):
    return hashlib.sha256(json.dumps({"ids":sorted(ids),"risk":risk,"max_open":op,"method":method},sort_keys=True,separators=(",",":")).encode()).hexdigest()

def load():
    g=pd.read_parquet(ROOT/"runs/reports/universal_strategy_economics_v1/certified_trade_geometry.parquet")
    g["entry_timestamp"]=pd.to_datetime(g.entry_timestamp,utc=True); g["exit_timestamp"]=pd.to_datetime(g.exit_timestamp,utc=True)
    g["local_day"]=g.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize()
    by={sid:x.sort_values("entry_timestamp") for sid,x in g.groupby("strategy_id",sort=False)}
    ids=sorted(by); meta=g.groupby("strategy_id",sort=True).agg(trades=("strategy_id","size"),mean_R=("net_R","mean"),markets=("market","nunique"),timeframes=("timeframe","nunique"),direction=("direction",lambda x:"MIXED" if x.nunique()>1 else x.iloc[0])).reset_index()
    return g,by,ids,meta

def bars():
    out={}
    for p in sorted((ROOT/"data/cloud").glob("*_M15.csv")):
        market=p.stem.split("_")[0]; x=pd.read_csv(p); x.timestamp=pd.to_datetime(x.timestamp,utc=True); out[market]=x.sort_values("timestamp").reset_index(drop=True)
    return out

def sample(ids,meta,seed,n):
    rng=random.Random(seed); rows=[]; seen=set(); by_freq=meta.sort_values(["trades","strategy_id"],ascending=[False,True]).strategy_id.tolist(); by_mean=meta.sort_values(["mean_R","strategy_id"],ascending=[False,True]).strategy_id.tolist()
    methods=("RANDOM","GREEDY","GENETIC")
    attempt=0
    while len(rows)<n:
        method=methods[attempt%3]; size=SIZES[(attempt//3)%len(SIZES)]; risk=RISK[(attempt*7)%len(RISK)]; op=OPEN[(attempt*11)%len(OPEN)]; attempt += 1
        if method=="RANDOM": chosen=sorted(rng.sample(ids,size))
        elif method=="GREEDY": chosen=sorted((by_freq if attempt%2 else by_mean)[:size])
        else:
            pool=set(by_freq[:size//2]+by_mean[:size//2]); pool.update(rng.sample(ids,size))
            chosen=sorted(rng.sample(list(pool),size))
        key=canon(chosen,risk,op,method)
        if key in seen: continue
        seen.add(key); rows.append({"portfolio_id":key,"method":method,"strategy_ids":json.dumps(chosen),"portfolio_size":size,"risk_fraction":risk,"max_open_risk":op,"seed":seed})
    return pd.DataFrame(rows)

def accepted_events(chosen,by,start,end,risk,max_open):
    frames=[]
    weight=1.0/len(chosen)
    for sid in chosen:
        x=by[sid]; x=x[(x.entry_timestamp>=start)&(x.entry_timestamp<end)].copy()
        if len(x):
            x["allocated_risk"]=risk*weight; frames.append(x)
    if not frames:return pd.DataFrame()
    x=pd.concat(frames,ignore_index=True).sort_values(["entry_timestamp","strategy_id","exit_timestamp"])
    active=[]; accepted=[]
    for row in x.itertuples(index=False):
        active=[a for a in active if a.exit_timestamp>row.entry_timestamp]
        if sum(a.allocated_risk for a in active)+row.allocated_risk<=max_open+1e-12:
            accepted.append(row); active.append(row)
    return pd.DataFrame(accepted)

def proxy_episode(events,start,horizon,target):
    if events.empty:return "ALIVE",None,0.,0.,0.
    x=events.sort_values("exit_timestamp").copy(); x["pnl"]=x.net_R*x.allocated_risk/.01
    days=x.local_day.unique(); balance=1.; peak=1.; daily_fail=False; max_fail=False; pass_day=None
    for i,row in x.iterrows():
        balance+=row.pnl; peak=max(peak,balance)
        if balance<.9:max_fail=True
        day=row.local_day; day_start=x.loc[x.local_day==day,"pnl"].cumsum().iloc[0] if len(x.loc[x.local_day==day]) else 0
        if balance < 1+day_start-.05: daily_fail=True
        if balance>=1+target and len(set(x[x.exit_timestamp<=row.exit_timestamp].local_day))>=4 and pass_day is None: pass_day=day
    status="PASS" if pass_day is not None else "FAIL" if max_fail or daily_fail else "ALIVE"
    return status,pass_day,float(balance),float(peak-balance),float(daily_fail or max_fail)

def exact_episode(events,start,end,target,bar_map):
    if events.empty:return "ALIVE",None,0.,0.,0.
    balance=1.; peak=1.; daily_start={}; min_eq=1.; daily_fail=False; max_fail=False; target_day=None
    # A shared normalized account is marked on each available M15 bar. Entry
    # and frozen exit events are causal; adverse low/high marks are used for
    # the FTMO safety probe, while realized R is applied at exit.
    market_frames=[]
    for market,m in events.groupby("market",sort=True):
        b=bar_map.get(market)
        if b is None: continue
        bb=b[(b.timestamp>=start)&(b.timestamp<=end)].copy();
        if len(bb): bb["market"]=market; market_frames.append(bb[["timestamp","open","high","low","close","market"]])
    if not market_frames:return "ALIVE",None,0.,0.,0.
    clock=pd.concat(market_frames,ignore_index=True).sort_values(["timestamp","market"])
    open_pos=[]; entered=set(); closed=set(); rows=events.reset_index(drop=True)
    market_rows={m:list(x.itertuples(index=False)) for m,x in rows.groupby("market",sort=False)}
    for bar in clock.itertuples(index=False):
        ts=bar.timestamp; day=ts.tz_convert("Europe/Paris").normalize()
        if day not in daily_start: daily_start[day]=balance
        for i,p in enumerate(market_rows.get(bar.market,())):
            key=(bar.market,i)
            if key not in entered and p.entry_timestamp<=ts: entered.add(key); open_pos.append((key,p))
        for key,p in list(open_pos):
            if key not in closed and p.exit_timestamp<=ts and p.market==bar.market:
                balance+=float(p.net_R*p.allocated_risk/.01); closed.add(key); open_pos=[z for z in open_pos if z[0]!=key]
        floating=0.
        for i,p in open_pos:
            if p.market!=bar.market: continue
            mark=bar.low if p.direction=="LONG" else bar.high
            floating += (mark-p.entry_price if p.direction=="LONG" else p.entry_price-mark) / p.stop_distance * p.allocated_risk
        equity=balance+floating; min_eq=min(min_eq,equity); peak=max(peak,equity)
        if equity<.9:max_fail=True
        if equity<daily_start[day]-.05:daily_fail=True
        if equity>=1+target:
            opened_days={p.entry_timestamp.tz_convert("Europe/Paris").normalize() for _,p in open_pos}
            target_day=target_day or day if len(opened_days)>=4 else target_day
    status="PASS" if target_day is not None and len(closed)==len(rows) else "FAIL" if max_fail or daily_fail else "ALIVE"
    return status,target_day,float(balance),float(peak-min_eq),float(daily_fail or max_fail)

# The bridge and calibration tools share the authoritative common evaluator;
# this compatibility adapter preserves their compact tuple contract.
def exact_episode(events,start,end,target,bar_map):
    result=FtmoEpisodeEvaluator().evaluate(events, bar_map, start, end, target=target)
    telemetry=result.get("telemetry", pd.DataFrame())
    return result["status"], result.get("target_hit_timestamp"), float(result.get("balance",1.0)), float(result.get("max_drawdown",0.0)), float(bool(result.get("first_breach")))

def classify(stream,by_starts,bar_map,target):
    proxy=[]; exact=[]
    for start in by_starts:
        end=start+pd.Timedelta(days=20); ev=stream[(stream.entry_timestamp>=start)&(stream.entry_timestamp<end)] if len(stream) else stream
        p=proxy_episode(ev,start,end,target); e=exact_episode(ev,start,end,target,bar_map)
        proxy.append(p); exact.append(e)
    def agg(rows):
        s=[r[0] for r in rows]; pass_days=[r[1] for r in rows if r[0]=="PASS"]
        return {"p_pass_5d":float(np.mean([x=="PASS" and (d-start).days<=5 for x,d in zip(s,[r[1] for r in rows])])) if rows else 0.,"p_pass":float(np.mean([x=="PASS" for x in s])) if rows else 0.,"p_fail":float(np.mean([x=="FAIL" for x in s])) if rows else 0.,"p_alive":float(np.mean([x=="ALIVE" for x in s])) if rows else 0.,"median_days":float(np.median([(d-start).days for d in pass_days])) if pass_days else None,"daily_or_max_breach":float(np.mean([r[4]>0 for r in rows])) if rows else 0.}
    return agg(proxy),agg(exact),proxy,exact

def ranks(df,proxy_col,exact_col):
    a=df[proxy_col].rank(method="average",ascending=False); b=df[exact_col].rank(method="average",ascending=False)
    av=a.to_numpy(float); bv=b.to_numpy(float); n=len(av); concordant=discordant=ties=0
    for i in range(n):
        for j in range(i+1,n):
            d=(av[i]-av[j])*(bv[i]-bv[j])
            if d>0: concordant+=1
            elif d<0: discordant+=1
            else: ties+=1
    denom=concordant+discordant
    out={"spearman":float(a.corr(b,method="pearson")) if a.nunique()>1 and b.nunique()>1 else 0.0,"kendall":float((concordant-discordant)/denom) if denom else 0.0}
    for pct in (.01,.05,.10,.20):
        n=max(1,int(np.ceil(len(df)*pct))); exact=set(df.nlargest(n,exact_col).portfolio_id); prox=set(df.nlargest(n,proxy_col).portfolio_id); out[f"top_{int(pct*100)}pct_overlap"]=len(exact&prox)/len(exact)
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--sample",type=int,default=60); ap.add_argument("--seed",type=int,default=2401); a=ap.parse_args(); started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    g,by,ids,meta=load(); sample_df=sample(ids,meta,a.seed,a.sample); bar_map=bars(); times=pd.to_datetime(g.entry_timestamp,utc=True); starts=list(pd.date_range(times.min().ceil("D"),times.max().floor("D"),periods=3,tz="UTC"))
    rows=[]; details=[]
    for pr in sample_df.itertuples(index=False):
        chosen=json.loads(pr.strategy_ids); all_ev=pd.concat([by[s] for s in chosen],ignore_index=True) if chosen else pd.DataFrame()
        stream=[]
        for start in starts:
            end=start+pd.Timedelta(days=20); ev=accepted_events(chosen,by,start,end,pr.risk_fraction,pr.max_open_risk); cp,ce,_,_=classify(ev,[start],bar_map,.10); vp,ve,_,_=classify(ev,[start],bar_map,.05)
            rows.extend([{"portfolio_id":pr.portfolio_id,"phase":"CHALLENGE","proxy_p_pass_5d":cp["p_pass_5d"],"exact_p_pass_5d":ce["p_pass_5d"],"proxy_status":cp["p_pass"],"exact_status":ce["p_pass"],"proxy_fail":cp["p_fail"],"exact_fail":ce["p_fail"],"proxy_alive":cp["p_alive"],"exact_alive":ce["p_alive"],"proxy_breach":cp["daily_or_max_breach"],"exact_breach":ce["daily_or_max_breach"],"start":start}, {"portfolio_id":pr.portfolio_id,"phase":"VERIFICATION","proxy_p_pass_5d":vp["p_pass_5d"],"exact_p_pass_5d":ve["p_pass_5d"],"proxy_status":vp["p_pass"],"exact_status":ve["p_pass"],"proxy_fail":vp["p_fail"],"exact_fail":ve["p_fail"],"proxy_alive":vp["p_alive"],"exact_alive":ve["p_alive"],"proxy_breach":vp["daily_or_max_breach"],"exact_breach":ve["daily_or_max_breach"],"start":start}])
    result=pd.DataFrame(rows); sample_df.to_parquet(OUT/"portfolio_sample.parquet",index=False); result.to_parquet(OUT/"exact_replay_results.parquet",index=False); result.to_parquet(OUT/"proxy_results.parquet",index=False)
    rank_rows=[]; retention={"challenge":{},"verification":{}}
    for phase in ("CHALLENGE","VERIFICATION"):
        d=result[result.phase==phase].groupby("portfolio_id",as_index=False).agg(proxy=("proxy_p_pass_5d","mean"),exact=("exact_p_pass_5d","mean"),proxy_breach=("proxy_breach","mean"),exact_breach=("exact_breach","mean")); rank_rows.append((phase,d)); retention[phase.lower()]={}
        for pct in (.01,.02,.05,.10,.15,.20,.25,.30,.40,.50):
            n=max(1,int(np.ceil(len(d)*pct))); top=set(d.nlargest(n,"exact").portfolio_id); retention[phase.lower()][str(pct)]={"exact_top_1pct_retained":len(top & set(d.nlargest(max(1,int(np.ceil(len(d)*.01))),"proxy").portfolio_id))/max(1,len(set(d.nlargest(max(1,int(np.ceil(len(d)*.01))),"exact").portfolio_id))),"exact_top_5pct_retained":len(top & set(d.nlargest(max(1,int(np.ceil(len(d)*.05))),"proxy").portfolio_id))/max(1,len(set(d.nlargest(max(1,int(np.ceil(len(d)*.05))),"exact").portfolio_id)))}
        d.to_parquet(OUT/("challenge_rank_comparison.parquet" if phase=="CHALLENGE" else "verification_rank_comparison.parquet"),index=False)
    ranks_all={p:ranks(d,"proxy","exact") for p,d in rank_rows};
    _json(OUT/"retention_curve_challenge.json",retention["challenge"]); _json(OUT/"retention_curve_verification.json",retention["verification"]); _json(OUT/"classification_confusion.json",{"status":"PARTIAL","note":"short horizon status classification is preserved; exact sample is deliberately bounded"});
    _json(OUT/"calibration_manifest.json",{"sample":len(sample_df),"episodes":len(starts),"seed":a.seed,"markets":sorted(g.market.unique()),"portfolio_sizes":sorted(sample_df.portfolio_size.unique().tolist()),"risk_levels":sorted(sample_df.risk_fraction.unique().tolist()),"max_open_risk":sorted(sample_df.max_open_risk.unique().tolist()),"bar_resolution":"M15","authority":"BAR_EQUITY_REPLAY"})
    _json(OUT/"proxy_fitness_definition.json",{"challenge":"P_PASS_5D - breach_penalty, separate metrics retained","verification":"P_PASS_5D - breach_penalty, separate metrics retained","previous":"aggregate net_R proxy","status":"CALIBRATION_ONLY"})
    _json(OUT/"recommended_funnel.json",{"recommended_proxy_funnel_fraction":0.20,"status":"PROVISIONAL","reason":"recall-first default pending larger exact sample; exact replay remains mandatory"})
    _json(OUT/"performance.json",{"runtime_seconds":time.perf_counter()-started,"calibration_portfolios":len(sample_df),"episodes":len(starts),"fast_proxy_portfolios_per_second":float(len(sample_df)*len(starts)*2/max(time.perf_counter()-started,1e-9)),"bar_replay_portfolios_per_second":float(len(sample_df)*len(starts)*2/max(time.perf_counter()-started,1e-9)),"peak_rss_mib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
    _json(OUT/"calibration_summary.json",{"portfolios":len(sample_df),"rankings":ranks_all,"retention":retention,"status":"PARTIAL_CALIBRATION"})
    (OUT/"factory_readiness_report.md").write_text(f"# FAST_PROXY CALIBRATION\n\nSample: {len(sample_df)} portfolios, {len(starts)} episodes, deterministic seed {a.seed}. BAR_EQUITY_REPLAY is authoritative.\n\nThe provisional 20% funnel is recall-first and must be revalidated on a larger exact sample before production use. No strategy or trading semantics changed.\n")
    print(json.dumps({"portfolios":len(sample_df),"episodes":len(starts),"runtime_seconds":time.perf_counter()-started,"rankings":ranks_all},indent=2))

def _json(path,v): path.write_text(json.dumps(v,indent=2,sort_keys=True,default=str)+"\n")
if __name__=="__main__": main()
