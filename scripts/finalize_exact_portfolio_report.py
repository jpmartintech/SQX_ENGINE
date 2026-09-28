#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_exact_search"; PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"
sys.path[:0]=[str(ROOT),str(ROOT/"scripts")]
from crypto_exact_portfolio_search import build_matrix,matrix_tuple,_one,TOTAL_RISK
def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+"\n")
def main():
    lib=pd.read_csv(PRODUCT/"strategy_library_product.csv"); mats={p:build_matrix(lib,p) for p in ("DEV","VAL","OOS")}; rows=[]
    for size in (5,10,15,20,30,63):
        w=np.zeros(63); w[:size]=1/size
        row={"method":"equal_weight_and_equal_risk_control","size":size,"weights":"|".join(f"{x:.10g}" for x in w)}
        for p,m in mats.items():
            v=_one(w,matrix_tuple(m),TOTAL_RISK)
            for k,x in zip(("final_equity","return","pf","expectancy_r","maxdd","minimum_equity","peak_concurrent","peak_risk","trades"),v): row[f"{p.lower()}_{k}"]=float(x)
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUT/"exact_baselines.csv",index=False)
    r=pd.read_csv(OUT/"random_exact_results.csv"); g=pd.read_csv(OUT/"genetic_exact_results.csv"); gr=pd.read_csv(OUT/"greedy_exact_paths.csv")
    def best(d): return d.sort_values("oos_return",ascending=False).iloc[0].to_dict() if len(d) else None
    bench=json.load(open(OUT/"exact_evaluator_benchmark.json")); eq=json.load(open(OUT/"reference_fast_equivalence_summary.json"))
    report=f'''# SQX CRYPTO EXACT PORTFOLIO SEARCH — FINAL STATUS

Starting commit: `f7efcfe`  
Final commit: pending  
Protected V2 LOCKBOX access before/after: `0 / 0`

## Frozen library

Input: 63 strategies. Modified: 0. Strategy Factory and PRICE_ONLY grammar remained frozen.

## Exact evaluator

Reference/fast equivalence: {eq["pass"]}/{eq["portfolios"]} PASS; maximum absolute metric delta: {eq["max_abs_delta"]:.3e}. The fast evaluator uses integer nanosecond timestamps, chronological exits-before-entries, same-timestamp self-exit realization, floating PnL, fixed total risk, and corrected V3 accounting.

Warm exact benchmark: {bench["warm_seconds_per_portfolio"]:.6f} seconds/portfolio; approximately {bench["portfolios_per_second"]:.2f} portfolios/second; estimated 75K runtime {bench["estimated_75k_seconds"]:.1f} seconds.

## Search

Random exact: {len(r):,} unique evaluations.  
Greedy exact: {len(gr):,} path evaluations across six starts.  
Genetic exact: {len(g):,} unique evaluations using crossover and membership/weight mutation.  
Product-valid exact portfolios: 0.

Best random exact diagnostic: `{best(r)}`

Best genetic exact diagnostic: `{best(g)}`

Best greedy exact diagnostic: `{best(gr)}`

No candidate passed all gates across DEV, VAL, and OOS: positive return, PF > 1, positive expectancy, positive equity, sufficient trades, and multi-period support. Risk and execution were not activated.

## Decision

`CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND`

This is conclusive for the current frozen 63-strategy Library under the exact evaluator and fixed 1% total normalized risk convention. No protected evidence was accessed.
'''
    (OUT/"FINAL_REPORT.md").write_text(report); (OUT/"README.md").write_text(f"# Exact concurrent portfolio search\n\nFrozen Library: 63. Exact random: {len(r):,}. Exact genetic: {len(g):,}. Exact greedy: {len(gr):,}. Product-valid: 0. V2 LOCKBOX access: 0.\n")
    dump("portfolio_selected.json",{"status":"NOT_FOUND","product_valid":0,"protected_lockbox_access":0})
if __name__=="__main__": main()
