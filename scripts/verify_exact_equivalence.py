#!/usr/bin/env python3
"""Reference/fast equivalence audit for the exact portfolio evaluator."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_exact_search"; PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"scripts"))
from crypto_exact_portfolio_search import build_matrix, matrix_tuple, _one, make_candidates, TOTAL_RISK
from sqx_engine.crypto.portfolio_v3 import replay_concurrent
def reference(m,w,assets):
    keep=w[m.strategy]>0
    frame=pd.DataFrame({"strategy_key":[str(int(x)) for x in m.strategy[keep]],"hash":[str(int(x)) for x in m.strategy[keep]],"asset":[assets[int(x)] for x in m.asset[keep]],"direction":["LONG" if x==1 else "SHORT" for x in m.direction[keep]],"entry_time":pd.to_datetime(m.times[m.entry[keep]],utc=True),"exit_time":pd.to_datetime(m.times[m.exit[keep]],utc=True),"r":m.r[keep],"entry_price":m.entry_price[keep],"exit_price":m.exit_price[keep]})
    bars={a:pd.DataFrame({"timestamp":pd.to_datetime(m.times,utc=True),"close":m.prices[:,i]}) for i,a in enumerate(assets)}
    return replay_concurrent(frame,bars,initial_equity=1.0,total_risk=TOTAL_RISK,weights={str(i):float(w[i]) for i in range(len(w))})
def main():
    lib=pd.read_csv(PRODUCT/"strategy_library_product.csv"); assets=sorted(lib.asset.unique()); m=build_matrix(lib,"VAL"); w,_=make_candidates(100,20261072); rows=[]
    for i in range(100):
        f=_one(w[i],matrix_tuple(m),TOTAL_RISK); r=reference(m,w[i],assets)
        vals=[float(r.total_return),float(r.profit_factor),float(r.expectancy_r),float(r.max_drawdown),float(r.minimum_equity),float(r.peak_concurrent),float(r.peak_risk),float(len(r.trades))]
        fast=[float(f[1]),float(f[2]),float(f[3]),float(f[4]),float(f[5]),float(f[6]),float(f[7]),float(f[8])]
        delta=max(abs(a-b) if np.isfinite(a) and np.isfinite(b) else 0.0 for a,b in zip(vals,fast)); rows.append({"portfolio":i,"max_abs_delta":delta,"equivalent":delta<=1e-9})
    pd.DataFrame(rows).to_csv(OUT/"reference_fast_equivalence.csv",index=False); summary={"portfolios":100,"pass":int(sum(x["equivalent"] for x in rows)),"fail":int(sum(not x["equivalent"] for x in rows)),"max_abs_delta":float(max(x["max_abs_delta"] for x in rows)),"tolerance":1e-9}; (OUT/"reference_fast_equivalence_summary.json").write_text(json.dumps(summary,indent=2)+"\n"); print(summary)
if __name__=="__main__": main()
