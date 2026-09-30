#!/usr/bin/env python3
import json, subprocess
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_multicoin_portfolio_v1'
def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,default=str)+'\n')
def q(s):
    s=pd.Series(s,dtype=float).dropna(); return {'p50':float(s.quantile(.5)) if len(s) else None,'p75':float(s.quantile(.75)) if len(s) else None,'p90':float(s.quantile(.9)) if len(s) else None}
def main():
    o=pd.read_parquet(OUT/'OOS_MULTICOIN_DIAGNOSTIC.parquet'); f=pd.read_parquet(OUT/'DEV_VAL_FRONTIER.parquet'); allx=pd.concat([pd.read_parquet(OUT/x) for x in ['RANDOM_PORTFOLIOS.parquet','GREEDY_PORTFOLIOS.parquet','GENETIC_PORTFOLIOS.parquet']],ignore_index=True); pool=pd.read_parquet(OUT/'SEARCH_POOL.parquet')
    multi=o[o.asset_count>1]; assets={a:int(o.members.str.split('|').map(lambda x:pool.iloc[[int(i) for i in x]].asset.eq(a).any()).sum()) for a in ['BTC','AVAX','ETH','LINK','SOL']}
    dump(OUT/'ASSET_ABLATION.json',{'method':'descriptive frozen-frontier asset presence; no OOS selection','frontier_asset_presence':assets,'multi_asset_frontier_count':int((o.asset_count>1).sum()),'btc_only_frontier_count':int((o.asset_count==1).sum()),'oos_used_for_selection':False})
    dump(OUT/'MARGINAL_ASSET_VALUE.json',{'frontier_frequency':assets,'method':'presence on frozen DEV+VAL frontier, not a causal marginal attribution','oos_used':False})
    dump(OUT/'LEAVE_ONE_ASSET_OUT.json',{'status':'not used to select portfolios; no OOS retuning','note':'frozen frontier candidates retain member identities for next exact risk-stage audit'})
    dump(OUT/'PROFIT_CONCENTRATION.json',{'multi_asset_frontier_count':int((o.asset_count>1).sum()),'single_asset_frontier_count':int((o.asset_count==1).sum()),'oos_median_return':float(o.oos_return.median()),'method':'frontier asset-count concentration diagnostic','research_only':True})
    dump(OUT/'DOWNSIDE_COINCIDENCE.json',{'status':'not claimed from standalone summaries','reason':'aligned strategy PnL correlation and drawdown overlap must be implemented before any risk decision','oos_used':False})
    dump(OUT/'BTC_VS_MULTICOIN_OOS.json',{'btc_only_control':{'frozen_frontier_count':44,'positive_rate':0.636,'median_return':0.0111,'status':'previously burned BTC portfolio diagnostic'},'multicoin':{'frontier_count':len(o),'positive_rate':float((o.oos_return>0).mean()),'median_return':float(o.oos_return.median()),'median_pf':float(o.oos_pf.median()),'median_maxdd':float(o.oos_maxdd.median())},'comparison':'multi-coin did not improve burned OOS research result under this search','research_only':True})
    dump(OUT/'PORTFOLIO_GENERALIZATION.json',{'dev_val_frontier':len(f),'oos_frontier':len(o),'positive_oos':int((o.oos_return>0).sum()),'positive_rate':float((o.oos_return>0).mean()),'median_oos_return':float(o.oos_return.median()),'median_oos_pf':float(o.oos_pf.median()),'median_oos_maxdd':float(o.oos_maxdd.median()),'multi_asset_positive_oos':int((multi.oos_return>0).sum()),'multi_asset_oos_count':len(multi),'btc_control_positive_rate':0.636,'research_only':True,'lockbox_access':0})
    report=f'''# SQX MULTI-COIN PORTFOLIO FACTORY V1 — FINAL STATUS

Starting commit: `7e5bc9e273a710229a402a6869ca65ee583df61d`
PRE-OOS freeze commit: `c68d270669573d1a1e479b154a83d43e1ff3aa24`
Primary assets: BTC, AVAX, ETH, LINK, SOL

## Search

Full frozen library: 92,109 instances. Search pool: 200 instances, 40 per asset, DEV+VAL-only deterministic top/middle LONG/SHORT tiers. Random: 50,000 unique. Greedy: 45 evaluations. Genetic: 100,000 unique.

## Engine

Exact chronological multi-asset shared-equity replay passed the 20 independent Python reference checks recorded in `PORTFOLIO_ENGINE_EQUIVALENCE.json`; 500 fast candidates were searched. Total intended heat is 1% shared across active weighted strategy instances. No OOS influenced the search.

## DEV+VAL

Frozen frontier records: {len(f)}. The search contained {int(allx.product_valid.sum())} DEV+VAL-valid candidates. The final frontier is dominated by single-asset candidates: {int((f.asset_count==1).sum())}; multi-asset candidates: {int((f.asset_count>1).sum())}.

## Burned OOS diagnostic

Frozen frontier tested: {len(o)}. Positive: {int((o.oos_return>0).sum())} ({(o.oos_return>0).mean():.1%}). Median return: {o.oos_return.median():.4f}. Median PF: {o.oos_pf.median():.4f}. Median MaxDD: {o.oos_maxdd.median():.4f}. This is burned research only.

BTC-only frozen control: 44 portfolios, 63.6% positive, median return +1.11% from the prior burned BTC portfolio diagnostic. The multi-coin frontier did not improve this control: its positive rate and median return were materially worse.

## Limitations

The exact engine and heat accounting are implemented, but a complete event-aligned PnL correlation/drawdown matrix across the 92k universe was not used to select portfolios. This loop therefore does not support a claim that cross-asset diversification improved the frontier.

## Decision

**MULTICOIN_PORTFOLIO_FACTORY_WEAK**

The current construction overfits DEV+VAL and is not ready for Risk Engine. Do not open LOCKBOX. Next action: redesign the portfolio search/persistence layer using DEV+VAL event-aligned behavioral fingerprints, then rerun the portfolio factory before Risk Engine.
'''
    (OUT/'FINAL_REPORT.md').write_text(report)
if __name__=='__main__': main()
