#!/usr/bin/env python
"""Apply the frozen V1.2 PRICE factory to V2 assets and cycles."""
from __future__ import annotations
import json, time
from pathlib import Path
import pandas as pd
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.generator import CryptoGeneticGenerator
from sqx_engine.strategy import StrategyDefinition

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_factory_v2"
ASSETS=("SOL","XRP","DOGE"); TFS=("M15","H1"); BUDGET=10_000; WALK=2_000; COST=.0009
CYCLES=[(1,"2023-01-01","2024-07-01","2024-07-01","2025-01-01","META_DEVELOPMENT"),(2,"2023-07-01","2025-01-01","2025-01-01","2025-07-01","META_DEVELOPMENT"),(3,"2024-01-01","2025-07-01","2025-07-01","2026-01-01","META_VALIDATION"),(4,"2024-07-01","2026-01-01","2026-01-01","2026-07-01","META_VALIDATION")]

def path(asset,tf): return ROOT/"data/crypto_portfolio_v2/canonical"/f"{asset}_{tf}_signal_market_binance.parquet"
def load(asset,tf):
    f=pd.read_parquet(path(asset,tf)); f["timestamp"]=pd.to_datetime(f.timestamp_open,utc=True)
    scale=float(f.close.iloc[0])
    for c in ("open","high","low","close"): f[c]=f[c].astype(float)/scale
    return f.reset_index(drop=True)
def bounds(f,a,b):
    idx=pd.DatetimeIndex(f.timestamp); return int(idx.searchsorted(pd.Timestamp(a,tz="UTC"))),int(idx.searchsorted(pd.Timestamp(b,tz="UTC")))
def search(f,asset,tf,a,b,budget,seed):
    s,e=bounds(f,a,b); features=prepare_crypto_features(f,None,"PRICE")
    ev=FastEvaluator(f,features,initial_capital=1.,spread=COST,engine="numba")
    gen=CryptoGeneticGenerator(asset,tf,seed=seed,min_predicates=1,max_predicates=2,grammar_version="v1.7",information_variant="PRICE",population_size=40,mode="scale")
    rows=[]
    for _ in range(budget):
        st=gen.ask(); r=ev.evaluate(st,start=s,end=e,rich=False); gen.tell(st,r)
        if r.trade_count>=20 and r.profit_factor>1:
            rows.append({"strategy":st.to_json(),"hash":st.canonical_hash,"asset":asset,"timeframe":tf,"train_pf":r.profit_factor,"train_expectancy_r":r.expectancy_r,"train_trades":r.trade_count,"train_return":r.return_pct,"train_maxdd":r.max_drawdown,"generation_budget":budget})
    rows=sorted(rows,key=lambda x:(x["train_expectancy_r"],x["train_pf"],-x["train_maxdd"],x["hash"]),reverse=True)[:50]
    return rows
def forward(rows,f,asset,tf,a,b):
    s,e=bounds(f,a,b); ev=FastEvaluator(f,prepare_crypto_features(f,None,"PRICE"),initial_capital=1.,spread=COST,engine="numba"); out=[]
    for row in rows:
        r=ev.evaluate(StrategyDefinition.from_json(row["strategy"]),start=s,end=e,rich=False)
        out.append({**row,"forward_pf":r.profit_factor,"forward_expectancy_r":r.expectancy_r,"forward_trades":r.trade_count,"forward_return":r.return_pct,"forward_maxdd":r.max_drawdown})
    return out
def main():
    started=time.perf_counter(); dev=[]; walk=[]
    for ai,asset in enumerate(ASSETS):
      for ti,tf in enumerate(TFS):
        f=load(asset,tf)
        # 10K is the frozen V2 new-asset development budget; later cycles use
        # a bounded 2K replay to establish portability without gate retuning.
        for ci,ta,tb,fa,fb,split in CYCLES:
            budget=BUDGET if ci==1 else WALK
            rows=search(f,asset,tf,ta,tb,budget,41000+ai*100+ti*10+ci)
            fw=forward(rows,f,asset,tf,fa,fb)
            walk.extend([{**r,"cycle_id":ci,"meta_split":split,"train_start":ta,"train_end":tb,"forward_start":fa,"forward_end":fb} for r in fw])
            if ci==1: dev.extend([{**r,"cycle_id":ci,"meta_split":split} for r in fw])
    OUT.mkdir(parents=True,exist_ok=True); df=pd.DataFrame(walk); df.to_parquet(OUT/"new_asset_factory_results.parquet",index=False); df.to_parquet(OUT/"asset_walk_forward.parquet",index=False)
    stats=df.groupby(["asset","timeframe","meta_split"]).agg(records=("hash","size"),eligible=("hash","nunique"),median_forward_pf=("forward_pf","median"),median_forward_expectancy=("forward_expectancy_r","median"),forward_survival=("forward_return",lambda x:float((x>0).mean())),median_maxdd=("forward_maxdd","median")).reset_index()
    stats.to_json(OUT/"new_asset_factory_summary.json",orient="records",indent=2)
    print(stats.to_string(index=False)); print(json.dumps({"runtime_seconds":time.perf_counter()-started,"rows":len(df)},indent=2))
if __name__=="__main__": main()
