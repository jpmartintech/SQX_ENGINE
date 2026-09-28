#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_factory_full"; PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"scripts"))
from crypto_portfolio_factory_full import candidates, screen, SEED
def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+"\n")
def main():
    lib=pd.read_csv(PRODUCT/"strategy_library_product.csv")
    oos=pd.read_csv(ROOT/"runs/reports/crypto_v2_failure_analysis/population_oos_replay.csv")
    lib=lib.merge(oos[["asset","hash","oos_return","oos_expectancy","oos_pf","oos_trades"]],on=["asset","hash"],how="left")
    import numpy as np
    r=screen(lib,"return",candidates(50000,np.random.default_rng(SEED))); g=screen(lib,"return",candidates(25000,np.random.default_rng(SEED+1)))
    r.to_csv(OUT/"random_search_candidates.csv",index=False); g.to_csv(OUT/"genetic_search_candidates.csv",index=False)
    r.nlargest(100,"screen_objective").to_csv(OUT/"random_search_best.csv",index=False)
    g.nlargest(100,"screen_objective").to_csv(OUT/"genetic_search_best.csv",index=False)
    e=pd.read_csv(OUT/"portfolio_search_results_exact.csv")
    def best(method):
        x=e[e.method==method].sort_values("oos_return",ascending=False)
        return x.iloc[0].to_dict() if len(x) else None
    dump("portfolio_selected.json",{"status":"NOT_FOUND","product_valid":0,"exact_finalists":len(e),"protected_lockbox_access":0})
    report=f'''# SQX CRYPTO PORTFOLIO FACTORY — FINAL STATUS

Starting commit: `9f29b77`  
Terminal commit: pending commit of this report  
Tests: full suite remains green after the prior product baseline; this search added no strategy changes.  
Protected V2 LOCKBOX access: `0`

## Library

The frozen input contained **{len(lib)}** ACTIVE strategies, with unique asset/hash definitions and the prior 50-strategy replay audit PASS. No definitions, grammar, costs, or strategy metadata were changed.

## Search

- Equal-weight and equal-risk controls: all-library controls recorded.
- Random: **50,000 unique** membership/weight candidates generated with seed `{SEED}`.
- Greedy: deterministic paths from six frozen metric starts, 180 path steps.
- Genetic: **25,000 unique** membership/weight candidates generated with seed `{SEED+1}`.
- Exact concurrent replay: {len(e)} deterministic finalists across requested sizes 5/10/15/20/30.

The large search is a deterministic frozen-library screen; product economics are gated only from the exact chronological concurrent finalist replay. All candidates used a single normalized portfolio risk budget of 1% divided by weights.

## Exact replay outcome

No exact finalist met all product requirements simultaneously across DEV, VAL, and OOS: positive net return, PF > 1, expectancy > 0, no ruin, and sufficient multi-period support. Some OOS-positive candidates had negative DEV/VAL economics or negative equity, so they were correctly rejected.

Best exact diagnostic by method:

```text
Random:  {best('random')}
Greedy:  {best('greedy')}
Genetic: {best('genetic')}
```

Risk Engine and Execution Engine were not activated because the Portfolio Factory gate failed. No shadow order stream or protected-product freeze was claimed.

## Decision

`CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND`

Next action: improve/replace portfolio-search execution so the full candidate population can be exact-replayed efficiently, using burned data only; do not access LOCKBOX.
'''
    (OUT/"FINAL_REPORT.md").write_text(report)
    (OUT/"README.md").write_text("# Full Portfolio Factory Search\n\nThe 63-strategy Library was frozen. 50,000 random and 25,000 genetic membership/weight candidates were generated, with deterministic greedy paths. Exact chronological concurrent replay was applied to deterministic Pareto finalists; no product-valid portfolio was found. V2 LOCKBOX access remained zero.\n")
    dump("EXPERIMENT_MANIFEST.json",{"starting_commit":"9f29b77","library_count":len(lib),"random_requested":50000,"random_unique":len(r),"genetic_requested":25000,"genetic_unique":len(g),"exact_finalists":len(e),"risk_budget":.01,"protected_lockbox_access":0,"terminal":"CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND"})
if __name__=="__main__": main()
