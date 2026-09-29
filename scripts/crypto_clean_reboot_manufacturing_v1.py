#!/usr/bin/env python3
"""Checkpointed DEV-only Random/Genetic manufacturing for clean reboot V1."""
from __future__ import annotations
import argparse, hashlib, json, os, pickle, sys, time
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'; PART=OUT/'parts'; OUT.mkdir(parents=True,exist_ok=True); PART.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from crypto_clean_reboot_v1 import load_source,bounds,evaluate_strategy
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.generator import CryptoRandomGenerator,CryptoGeneticGenerator
from sqx_engine.backtest.fast import FastEvaluator

def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+'\n')
def setup():
    d=load_source(); f=prepare_crypto_features(d,None,'PRICE'); ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine='numba',cache_size=0); b=bounds(d); st=int(d.timestamp.searchsorted(b['START'])); en=int(d.timestamp.searchsorted(b['DEV_END'])); cuts=np.linspace(st,en,7,dtype=int); wb=[(int(cuts[i]),int(cuts[i+1])) for i in range(6)]; return d,f,ev,st,en,wb
def persist(kind,rows,seq):
    if rows: pd.DataFrame(rows).to_parquet(PART/f'{kind}_{seq:06d}.parquet',index=False)
def load_parts(kind):
    files=sorted(PART.glob(f'{kind}_*.parquet')); return pd.concat([pd.read_parquet(x) for x in files],ignore_index=True) if files else pd.DataFrame()
def campaign(kind,target,seed,checkpoint_every=5000):
    d,f,ev,st,en,wb=setup(); ck=OUT/f'{kind}_checkpoint.pkl'; seen=set(); rows=[]; count=0; part=0; started=time.time(); gen=None
    if ck.exists():
        state=pickle.loads(ck.read_bytes()); seen=state['seen']; count=state['count']; part=state['part']; started=state['started']; gen=state['generator']; print(f'resuming {kind} at {count}',flush=True)
    else:
        gen=(CryptoRandomGenerator('BTC','M15',seed=seed,min_predicates=1,max_predicates=2,grammar_version='v1.7',information_variant='PRICE') if kind=='random' else CryptoGeneticGenerator('BTC','M15',seed=seed,min_predicates=1,max_predicates=2,grammar_version='v1.7',information_variant='PRICE',population_size=80,mode='scale'))
    attempts=0; duplicates=0
    while count<target:
        s=gen.ask(known_hashes=seen) if kind=='genetic' else gen.ask(); attempts+=1
        h=s.canonical_hash
        if h in seen: duplicates+=1; continue
        seen.add(h); row=evaluate_strategy(s,d,f,ev,st,en,wb); row['kind']=kind.upper(); rows.append(row); count+=1
        if kind=='genetic':
            class R: pass
            q=R(); q.expectancy_r=row['economic_expectancy']; q.sharpe=0.; q.max_drawdown=row['maxdd']; gen.tell(s,q)
        if len(rows)>=1000:
            persist(kind,rows,part); part+=1; rows=[]
        if count%checkpoint_every==0:
            persist(kind,rows,part); part+=1; rows=[]; pickle.dump({'kind':kind,'count':count,'attempts':attempts,'duplicates':duplicates,'seen':seen,'generator':gen,'part':part,'started':started},ck.open('wb')); print(json.dumps({'kind':kind,'unique':count,'attempts':attempts,'duplicates':duplicates,'sps':count/max(time.time()-started,1e-9)}),flush=True)
    persist(kind,rows,part); ck.unlink(missing_ok=True); result=load_parts(kind); result.to_parquet(OUT/f'{kind}_results.parquet',index=False)
    def pct(c,q): return float(result[c].quantile(q)) if len(result) else None
    dump(f'{kind}_summary.json',{'target':target,'unique_evaluated':len(result),'attempts':attempts,'duplicates':duplicates,'elapsed_seconds':time.time()-started,'strategies_per_second':len(result)/max(time.time()-started,1e-9),'long':int((result.direction=='LONG').sum()),'short':int((result.direction=='SHORT').sum()),'economically_valid':int(((~result.ruin)&(result.trades>0)).sum()), 'positive_return':int((result['return']>0).sum()),'positive_expectancy':int((result.economic_expectancy>0).sum()),'pf_gt_1':int((result.pf>1).sum()),'return_percentiles':{str(q):pct('return',q) for q in [.5,.75,.9,.95,.99]},'expectancy_percentiles':{str(q):pct('economic_expectancy',q) for q in [.5,.75,.9,.95,.99]},'lockbox_access':0})
    return result
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['prepare','dry-run','random','genetic'],required=True); ap.add_argument('--target',type=int); a=ap.parse_args()
    if a.phase=='prepare':
        dump('PRE_CAMPAIGN_MANIFEST.json',{'starting_commit':'e2f6311','dataset_sha256':'f2ddfd9b85f4e7556474e1ef10f78eebd927a0f0e330785d48b4d08e5b69a20a','split':'60/15/15/10 elapsed time','economic_contract':'frozen bounded 1% heat','grammar':'v1.7 PRICE_ONLY','fitness':'frozen profit-first','random_target':50000,'genetic_target':200000,'val_access_before':0,'oos_access_before':0,'lockbox_access_before':0}); dump('DATA_ACCESS_LEDGER.json',{'DEV_accesses':0,'VAL_accesses':0,'OOS_accesses':0,'LOCKBOX_accesses':0})
    elif a.phase=='dry-run':
        r=campaign('random',a.target or 100,7101,checkpoint_every=100); dump('CAMPAIGN_RUNTIME.json',{'phase':'dry-run','evaluated':len(r),'lockbox_access':0})
    elif a.phase=='random': campaign('random',a.target or 50000,1201)
    else: campaign('genetic',a.target or 200000,2201)
if __name__=='__main__': main()
