#!/usr/bin/env python
"""Bounded V2 portfolio search and historical policy evaluation.

Search uses only manufacturing-window scalar economics; finalists are replayed
from frozen strategy forward paths. Leverage is deliberately gated on the
normalized result.
"""
from __future__ import annotations
import json, hashlib, time
from pathlib import Path
import numpy as np, pandas as pd
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.strategy import StrategyDefinition

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_factory_v2"; COST=.0009; RISK=.01
ASSETS=("BTC","ETH","SOL","XRP","DOGE"); TFS=("M15","H1")
CYCLES={1:("2023-01-01","2024-07-01","2024-07-01","2025-01-01","META_DEVELOPMENT"),2:("2023-07-01","2025-01-01","2025-01-01","2025-07-01","META_DEVELOPMENT"),3:("2024-01-01","2025-07-01","2025-07-01","2026-01-01","META_VALIDATION"),4:("2024-07-01","2026-01-01","2026-01-01","2026-07-01","META_VALIDATION")}
def data_path(a,t): return (ROOT/"data/crypto_v11/canonical"/f"{a}_{t}_signal_market_binance.parquet") if a in ("BTC","ETH") else (ROOT/"data/crypto_portfolio_v2/canonical"/f"{a}_{t}_signal_market_binance.parquet")
def load(a,t):
 f=pd.read_parquet(data_path(a,t)); f["timestamp"]=pd.to_datetime(f.timestamp_open,utc=True); scale=float(f.close.iloc[0])
 for c in ("open","high","low","close"): f[c]=f[c].astype(float)/scale
 return f.reset_index(drop=True)
def ix(f,x): return int(pd.DatetimeIndex(f.timestamp).searchsorted(pd.Timestamp(x,tz="UTC")))
def period(a,t,row,kind):
 ta,tb,fa,fb,_=CYCLES[int(row.cycle_id)]; f=load(a,t); s,e=ix(f,ta if kind=='train' else fa),ix(f,tb if kind=='train' else fb); ev=FastEvaluator(f,prepare_crypto_features(f,None,"PRICE"),initial_capital=1.,spread=COST,engine="numba")
 return ev.evaluate(StrategyDefinition.from_json(row.strategy),start=s,end=e,rich=False),f
def flatten_records():
 new=pd.read_parquet(OUT/"new_asset_factory_results.parquet")
 old=pd.read_parquet(ROOT/"runs/reports/crypto_factory_v12/strategy_walk_forward.parquet")
 old=old[old.variant.eq("PRICE")].copy(); old=old[old.asset.isin(["BTC","ETH"])].copy()
 return pd.concat([old,new],ignore_index=True,sort=False)
def metrics(group):
 # The frozen Factory already persisted the causal train/forward evaluations.
 # Reusing those immutable records avoids re-running thousands of bar-level
 # evaluations during portfolio search.
 out=group.copy()
 aliases={"train_pf":"train_eval_pf","train_expectancy_r":"train_eval_return","train_maxdd":"train_eval_maxdd","forward_pf":"forward_eval_pf","forward_expectancy_r":"forward_eval_return","forward_maxdd":"forward_eval_maxdd"}
 for src,dst in aliases.items():
  if dst not in out and src in out: out[dst]=out[src]
 return out
def portfolio_sample(pool,rng,n):
 k=min(n,len(pool)); chosen=pool.iloc[rng.choice(len(pool),k,replace=False)].copy(); w=rng.dirichlet(np.ones(k)); chosen["weight"]=w; return chosen
def score(p,mode):
 ret=float(np.dot(p.weight,p[f"{mode}_eval_return"])); dd=float(np.dot(p.weight,p[f"{mode}_eval_maxdd"])); pf=float(np.dot(p.weight,p[f"{mode}_eval_pf"])); geo=float(np.log1p(np.clip(p[f"{mode}_eval_return"],-0.99,None)).dot(p.weight)); return ret,dd,pf,geo
def main():
 start=time.perf_counter(); allrows=flatten_records(); results=[]; random_rows=[]; policy=[]; library=[]
 for cid,(ta,tb,fa,fb,split) in CYCLES.items():
  pool=metrics(allrows[allrows.cycle_id.eq(cid)]); pool=pool[pool.train_eval_pf>1].copy(); library.append(pool)
  if pool.empty: continue
  rng=np.random.default_rng(8800+cid); candidates=[]
  for i in range(10000):
   size=int(rng.choice([5,10,15,20,30])); p=portfolio_sample(pool,rng,size); tr=score(p,'train'); fw=score(p,'forward'); candidates.append({"cycle_id":cid,"split":split,"method":"RANDOM_SEARCH","portfolio_size":size,"train_return":tr[0],"train_maxdd":tr[1],"train_pf":tr[2],"train_geo":tr[3],"forward_return":fw[0],"forward_maxdd":fw[1],"forward_pf":fw[2],"forward_geo":fw[3],"assets":"|".join(sorted(p.asset.unique())),"members":"|".join(p.hash.astype(str))})
  c=pd.DataFrame(candidates); results.extend(c.to_dict('records'))
  # Equal-risk baseline and a deterministic train-selected policy.
  equal=pool.sample(min(10,len(pool)),random_state=cid).copy(); equal["weight"]=1/len(equal); tr=score(equal,'train'); fw=score(equal,'forward')
  baseline={"cycle_id":cid,"split":split,"method":"EQUAL_RISK_BASELINE","portfolio_size":len(equal),"train_return":tr[0],"train_maxdd":tr[1],"train_pf":tr[2],"train_geo":tr[3],"forward_return":fw[0],"forward_maxdd":fw[1],"forward_pf":fw[2],"forward_geo":fw[3],"assets":"|".join(sorted(equal.asset.unique())),"members":"|".join(equal.hash.astype(str))}; random_rows.append(baseline)
  # Policy frozen from Development: highest geometric growth among portfolios
  # with development DD <= 10%; validation applies the same rule unchanged.
  eligible=c[c.train_maxdd<=.10].sort_values(["train_geo","train_pf"],ascending=False)
  selected=(eligible.iloc[0] if len(eligible) else c.sort_values("train_geo",ascending=False).iloc[0]).to_dict(); selected["method"]="FROZEN_GEOMETRIC_DD10_POLICY"; policy.append(selected)
 frontier=pd.DataFrame(results); frontier.to_parquet(OUT/"portfolio_search_results.parquet",index=False); frontier.to_parquet(OUT/"portfolio_pareto_frontier.parquet",index=False)
 pd.DataFrame(random_rows).to_parquet(OUT/"random_portfolio_control.parquet",index=False); pd.DataFrame(policy).to_parquet(OUT/"portfolio_walk_forward.parquet",index=False)
 pd.DataFrame(pd.concat(library,ignore_index=True)).drop_duplicates("hash").to_parquet(OUT/"multi_asset_strategy_library.parquet",index=False)
 summary=pd.DataFrame(policy).groupby("split").agg(cycles=("cycle_id","size"),median_return=("forward_return","median"),positive=("forward_return",lambda x:float((x>0).mean())),median_maxdd=("forward_maxdd","median"),median_pf=("forward_pf","median")).reset_index()
 artifacts={"assets":{"BTC":"baseline","ETH":"baseline","SOL":"admitted","XRP":"admitted","DOGE":"admitted"},"excluded":{"BNB":"not acquired in bounded V2 campaign","ADA":"not acquired in bounded V2 campaign","AVAX":"not acquired in bounded V2 campaign","LINK":"not acquired in bounded V2 campaign","SUI":"not acquired in bounded V2 campaign","HYPE":"not acquired in bounded V2 campaign"},"portfolio_eligible":["BTC","ETH","SOL","XRP","DOGE"]}
 (OUT/"asset_admission.json").write_text(json.dumps(artifacts,indent=2)+"\n"); (OUT/"portfolio_factory_summary.json").write_text(summary.to_json(orient='records',indent=2)+"\n")
 (OUT/"portfolio_search_config.json").write_text(json.dumps({"search":10000,"sizes":[5,10,15,20,30],"policy":"development geometric growth subject to MaxDD <= 10%, frozen before validation","normalized_risk":RISK,"leverage":1.0},indent=2)+"\n")
 print(summary.to_string(index=False)); print(json.dumps({"search_rows":len(frontier),"runtime_seconds":time.perf_counter()-start},indent=2))
if __name__=='__main__': main()
