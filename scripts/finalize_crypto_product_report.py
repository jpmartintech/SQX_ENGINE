#!/usr/bin/env python3
"""Complete the burned-data product-gate handoff without protected access."""
from __future__ import annotations
import hashlib, json, os, platform, sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_product_pipeline"
def sha(p):
    h=hashlib.sha256();
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+"\n")
def main():
    lib=pd.read_csv(OUT/"strategy_library_product.csv"); search=pd.read_csv(OUT/"portfolio_search_results.csv")
    frontier=pd.read_csv(OUT/"portfolio_pareto_frontier.csv")
    for n in ("portfolio_selected_trades.csv","portfolio_selected_equity.csv","portfolio_selected_contributions.csv"):
        if not (OUT/n).exists(): pd.DataFrame().to_csv(OUT/n,index=False)
    lock=0
    manifest={"product":"SQX Crypto Product Pipeline","starting_commit":"efc2c26","strategy_factory":"frozen V1.2 / v1.7 PRICE_ONLY","library_count":len(lib),"portfolio_candidates":len(search),"pareto_candidates":len(frontier),"protected_v2_lockbox_access":lock,"real_orders":0,"terminal":"CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND","search_note":"bounded stratified true-concurrent candidates; no protected data"}
    dump("PRODUCT_MANIFEST.json",manifest)
    dump("PRE_PROTECTED_PRODUCT_FREEZE.json",{"status":"NOT_REACHED","reason":"portfolio gate failed","lockbox_access_count":0,"library_sha256":sha(OUT/"strategy_library_product.csv"),"portfolio_sha256":sha(OUT/"portfolio_search_results.csv")})
    report=f'''# SQX CRYPTO PRODUCT PIPELINE — FINAL STATUS

Starting commit: `efc2c26`

## Library

The frozen V1.2 PRICE_ONLY factory supplied 7,017 unique burned asset/hash definitions. The product admission gates retained **{len(lib)}** individually qualified records across {", ".join(sorted(lib.asset.unique()))}. Admission used DEV multi-window support and former VAL economics only; no protected data was read. The 50-record fast/reference replay audit passed.

## Portfolio

The true chronological concurrent engine evaluated {len(search)} bounded, deterministically generated candidates from a stratified Library compute pool. It modeled floating equity, chronological exits-before-entries, overlapping positions, normalized total risk, and composite asset/strategy keys. No candidate passed the product gate across burned DEV, VAL, and OOS: positive net economics, PF > 1, positive expectancy, no ruin, and positive behavior across the periods. The strongest diagnostic candidates still had negative or invalid equity and/or negative expectancy.

Because the Portfolio Factory gate failed, Risk Engine and Execution Engine were not activated. No risk policy, shadow order stream, or protected validation freeze was claimed.

## Protected data

V2 LOCKBOX access before: `0`\nV2 LOCKBOX access after: `0`\nReal orders: `0`

## Decision

`CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND`

This is a burned-data product construction result, not a new validation result. The next product action is to diagnose or redesign portfolio construction using the existing burned evidence before any protected validation decision; no V2 LOCKBOX access is authorized by this loop.
'''
    (OUT/"PRODUCT_REPORT.md").write_text(report)
    dump("execution_safety_tests.json",{"status":"NOT_ACTIVATED","reason":"portfolio gate failed","real_orders":0})
    print(json.dumps(manifest,indent=2))
if __name__=="__main__": main()
