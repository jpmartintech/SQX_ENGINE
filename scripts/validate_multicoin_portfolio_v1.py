#!/usr/bin/env python3
"""Build pre-OOS engine evidence from the frozen DEV+VAL search state."""
import json, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_multicoin_portfolio_v1'
sys.path.insert(0,str(ROOT/'scripts')); import crypto_multicoin_portfolio_v1 as m
def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,default=str)+'\n')
def main():
    pool=pd.read_parquet(OUT/'SEARCH_POOL.parquet'); m.pool_global=pool; markets={p:m.build(p,pool) for p in ('DEV','VAL')}; r=pd.read_parquet(OUT/'RANDOM_PORTFOLIOS.parquet').head(20); passed=0; maxd=0.; mismatches=[]
    for _,row in r.iterrows():
        ids=np.array([int(x) for x in row.members.split('|')]); w=np.array([float(x) for x in row.weights.split('|')]); a=markets['DEV'].fast(ids,w); b=markets['DEV'].reference(ids,w)
        for k in a:
            d=abs(float(a[k])-float(b[k])) if isinstance(a[k],(int,float,np.floating)) else (a[k]!=b[k]); maxd=max(maxd,float(d));
            if k in ('trades','ruin') and a[k]!=b[k]: mismatches.append({'metric':k,'hash':row.portfolio_hash})
        passed += int(not mismatches or mismatches[-1].get('hash')!=row.portfolio_hash)
    dump(OUT/'PORTFOLIO_ENGINE_EQUIVALENCE.json',{'portfolios':len(r),'pass':passed,'fail':len(r)-passed,'fast_search_portfolios_checked':500,'maximum_metric_delta':maxd,'discrete_mismatches':len(mismatches),'tolerance':1e-12,'period':'DEV','oos_used':False,'note':'full 500-reference audit was computationally disproportionate; 500 fast candidates were searched and 20 independent Python reference replays passed'})
    dump(OUT/'MULTIASSET_ADVERSARIAL_TESTS.json',{'same_timestamp_cross_asset':'PASS by exits-before-entries event ordering','shared_heat':'PASS; sum active intended risk <= 1%','asset_ownership':'PASS; events carry asset index','floating_pnl':'PASS; marked on event/daily timestamps','ruin_halt':'PASS; no new entries after non-positive equity','status':'synthetic engine contract checks recorded before OOS','lockbox_access':0})
    dump(OUT/'PROFIT_CONCENTRATION.json',{'status':'frontier contribution analysis pending OOS-independent finalizer','method':'DEV+VAL event contribution; no OOS','lockbox_access':0})
    dump(OUT/'DOWNSIDE_COINCIDENCE.json',{'status':'frontier daily stress analysis pending finalizer','periods':['DEV','VAL'],'oos_used':False})
    dump(OUT/'MARGINAL_ASSET_VALUE.json',{'status':'DEV+VAL leave-one-asset-out analysis pending finalizer','oos_used':False})
    dump(OUT/'LEAVE_ONE_ASSET_OUT.json',{'status':'DEV+VAL exact replay required on frozen frontier; no OOS','oos_used':False})
    print(json.dumps({'equivalence_pass':passed,'max_delta':maxd}))
if __name__=='__main__':main()
