"""Minimal causal cooldown falsification probe; diagnostic only."""
from __future__ import annotations
import json, resource, time
from pathlib import Path
import numpy as np
import pandas as pd
from sqx_engine.portfolio_factory.exact_equity import FtmoEpisodeEvaluator
from prop_supervisor_diversification import DATA, ROOT, OUT, load_ohlcv, StrategyDefinition, FastEvaluator, prepare_features


def make_ledger(strategy, market, timeframe, frame):
    data = frame.iloc[:int(len(frame) * .80)].reset_index(drop=True)
    features = prepare_features(data, grammar_version="v1.7")
    ev = FastEvaluator(data, features, initial_capital=10000, spread=0.0, slippage=0.0, cache_size=0, engine="auto")
    times = {pd.Timestamp(t).tz_convert("UTC"): i for i, t in enumerate(data.timestamp)}; atr = np.asarray(features["atr_14"], dtype=float)
    rows = []
    for t in ev.evaluate(strategy, rich=True).trades:
        entry = pd.Timestamp(t["entry_time"], tz="UTC") if pd.Timestamp(t["entry_time"]).tzinfo is None else pd.Timestamp(t["entry_time"]).tz_convert("UTC"); exit_time = pd.Timestamp(t["exit_time"], tz="UTC") if pd.Timestamp(t["exit_time"]).tzinfo is None else pd.Timestamp(t["exit_time"]).tz_convert("UTC")
        ei=times[entry]; risk=float(atr[ei-1]*strategy.stop_atr); ep=float(data.open.iloc[ei]); sign=1 if t["direction"]=="LONG" else -1; stop=ep-risk if sign>0 else ep+risk; target=ep+risk*strategy.target_atr/strategy.stop_atr if sign>0 else ep-risk*strategy.target_atr/strategy.stop_atr; xp=stop if t["reason"]=="STOP" else target if t["reason"]=="TARGET" else float(data.close.iloc[times[exit_time]])
        rows.append({"strategy_id": strategy.readable_id, "market": market, "timeframe": timeframe, "direction": t["direction"], "entry_timestamp": entry, "exit_timestamp": exit_time, "entry_price": ep, "stop_price": stop, "target_price": target, "exit_price": xp, "net_R": t["r"]})
    x = pd.DataFrame(rows)
    if x.empty:
        return pd.DataFrame(columns=["strategy_id", "market", "timeframe", "direction", "entry_timestamp", "exit_timestamp", "entry_price", "stop_price", "target_price", "net_R", "prior_loss_streak"])
    x = x.sort_values("entry_timestamp")
    loss = x.net_R < 0; streak=[]; cur=0
    for bad in loss:
        streak.append(cur); cur = cur + 1 if bad else 0
    x["prior_loss_streak"] = streak
    return x


def accepted(members, by, start, end, risk, cap, cooldown):
    frames=[]; weight=1/len(members)
    for sid in members:
        x=by[sid]; x=x[(x.entry_timestamp>=start)&(x.entry_timestamp<end)].copy()
        if cooldown and "prior_loss_streak" in x: x=x[x.prior_loss_streak < cooldown]
        if len(x): x["allocated_risk"]=risk*weight; frames.append(x)
    if not frames:return pd.DataFrame()
    x=pd.concat(frames,ignore_index=True).sort_values(["entry_timestamp","strategy_id","exit_timestamp"]); active=[]; out=[]
    for row in x.itertuples(index=False):
        active=[a for a in active if a.exit_timestamp>row.entry_timestamp]
        if sum(a.allocated_risk for a in active)+row.allocated_risk<=cap+1e-12:out.append(row);active.append(row)
    return pd.DataFrame(out)


def main():
    started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    defs=pd.concat([pd.read_parquet(ROOT/'runs/reports/prop_strategy_factory_v1_autonomous_loop_02/forensics_eur/prop_candidates_replay.parquet'),pd.read_parquet(ROOT/'runs/reports/prop_strategy_factory_v1_autonomous_loop_02/forensics_xau/prop_candidates_replay.parquet')],ignore_index=True).drop_duplicates('strategy_id')
    selected=[]
    for _,g in defs.groupby(['market','timeframe'],sort=True):selected.extend(g.sort_values('strategy_id').strategy_id.head(5))
    by={};bars={}
    for (market,tf),g in defs[defs.strategy_id.isin(selected)].groupby(['market','timeframe'],sort=True):
        frame=load_ohlcv(DATA[(market,tf)]);bars.setdefault(market,load_ohlcv(DATA[(market,'M15')]))
        for row in g.itertuples(index=False):
            x=make_ledger(StrategyDefinition.from_json(row.strategy_json),market,tf,frame)
            if len(x):by[row.strategy_id]=x
    ids=sorted(by); allx=pd.concat(list(by.values()),ignore_index=True); days=sorted(allx.entry_timestamp.dt.tz_convert('Europe/Paris').dt.normalize().unique()); episodes=[(days[i],days[i+4]+pd.Timedelta(days=1),'DEVELOPMENT' if i<int((len(days)-4)*.6) else 'VALIDATION') for i in range(len(days)-4)][::max(1,(len(days)-4)//30)]
    families={'CROSS_MARKET_TIMEFRAME':ids,'CROSS_MARKET_M15':[x for x in ids if x in defs[(defs.timeframe=='M15')].strategy_id.tolist()]}
    rows=[]
    for fam,members in families.items():
      for policy,cool in [('BASELINE',0),('COOLDOWN_AFTER_2_LOSSES',2)]:
       for risk,cap in [(.01,.02),(.02,.03)]:
        for start,end,split in episodes:
         ev=accepted(members,by,start,end,risk,cap,cool)
         for target,phase in [(.10,'CHALLENGE'),(.05,'VERIFICATION')]:
          z=FtmoEpisodeEvaluator().evaluate(ev,bars,start,end,target=target);t=z.get('telemetry',pd.DataFrame())
          rows.append({'family':fam,'policy':policy,'risk':risk,'cap':cap,'split':split,'phase':phase,'status':z.get('status'),'max_intraperiod':float(t.equity.max()-1) if len(t) else 0.,'min_equity':float(t.equity.min()-1) if len(t) else 0.,'admitted':len(ev),'peak_open_risk':float(t.open_initial_risk.max()) if len(t) else 0.})
    result=pd.DataFrame(rows);result.to_parquet(OUT/'cooldown_exact_results.parquet',index=False)
    summary=[]
    for k,g in result.groupby(['family','policy','risk','cap','split','phase'],sort=True):
      fam,pol,risk,cap,split,phase=k;summary.append({'family':fam,'policy':pol,'risk':risk,'cap':cap,'split':split,'phase':phase,'episodes':len(g),'pass':float((g.status=='PASS').mean()),'fail':float(g.status.str.startswith('FAIL').mean()),'alive':float((g.status=='ALIVE').mean()),'p95_max_intraperiod':float(g.max_intraperiod.quantile(.95)),'p99_max_intraperiod':float(g.max_intraperiod.quantile(.99)),'max_max_intraperiod':float(g.max_intraperiod.max()),'p05_equity':float(g.min_equity.quantile(.05)),'peak_open_risk':float(g.peak_open_risk.max())})
    (OUT/'cooldown_probe.json').write_text(json.dumps({'authority':'FtmoEpisodeEvaluator','sample_strategies':len(ids),'results':summary,'oos_accesses':0,'falsification':'Cooldown is not justified for V2 unless Validation downside improves without disproportionate upper-tail/opportunity collapse.'},indent=2,sort_keys=True,default=str)+'\n')
    (OUT/'cooldown_performance.json').write_text(json.dumps({'runtime_seconds':time.perf_counter()-started,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'oos_accesses':0},indent=2)+'\n')
    print(json.dumps({'strategies':len(ids),'episodes':len(episodes),'rows':len(result),'runtime_seconds':time.perf_counter()-started,'oos_accesses':0},indent=2))
if __name__=='__main__':main()
