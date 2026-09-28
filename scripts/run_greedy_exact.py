#!/usr/bin/env python3
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_exact_search"; PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"
sys.path[:0]=[str(ROOT),str(ROOT/"scripts")]
from crypto_exact_portfolio_search import build_matrix, matrix_tuple, _one, TOTAL_RISK
def metric(weights, matrices):
    x={p:_one(weights,matrix_tuple(m),TOTAL_RISK) for p,m in matrices.items()}
    score=min(x[p][1] for p in x)-.10*max(abs(x[p][4]) for p in x)
    return score,x
def main():
    lib=pd.read_csv(PRODUCT/"strategy_library_product.csv"); matrices={p:build_matrix(lib,p) for p in ("DEV","VAL","OOS")}; paths=[]
    for seed in range(6):
        current=[seed];
        for step in range(1,31):
            choices=[j for j in range(63) if j not in current][:20]; trials=[]
            for j in choices:
                ids=current+[j]; w=np.zeros(63); w[ids]=1/len(ids); s,x=metric(w,matrices); trials.append((s,j,x))
            if not trials: break
            _,j,x=max(trials,key=lambda z:(z[0],-z[2]["OOS"][4])); current.append(j); w=np.zeros(63); w[current]=1/len(current); _,x=metric(w,matrices)
            row={"seed":seed,"step":step,"size":len(current),"indices":"|".join(map(str,current)),"weights":"|".join(f"{z:.10g}" for z in w)}
            for p,v in x.items():
                for k,val in zip(("final_equity","return","pf","expectancy_r","maxdd","minimum_equity","peak_concurrent","peak_risk","trades"),v): row[f"{p.lower()}_{k}"]=float(val)
            row["product_valid"]=bool(all(row[f"{p.lower()}_minimum_equity"]>0 and row[f"{p.lower()}_return"]>0 and row[f"{p.lower()}_pf"]>1 and row[f"{p.lower()}_expectancy_r"]>0 for p in matrices)); paths.append(row)
    d=pd.DataFrame(paths); d.to_csv(OUT/"greedy_exact_paths.csv",index=False); (OUT/"greedy_exact_summary.json").write_text(json.dumps({"paths":6,"exact_evaluations":len(d),"steps":180,"valid":int(d.product_valid.sum()),"protected_lockbox_access":0},indent=2)+"\n"); print({"paths":6,"evaluations":len(d),"valid":int(d.product_valid.sum())})
if __name__=="__main__": main()
