#!/usr/bin/env python3
"""Freeze the completed DEV manufacturing campaign before VAL access."""
from __future__ import annotations
import hashlib, json, subprocess, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'
PART=OUT/'parts'

def sha(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,default=str)+'\n')

def quantiles(d,col):
    x=pd.to_numeric(d[col],errors='coerce').replace([np.inf,-np.inf],np.nan).dropna()
    return {f'P{int(q*100)}':float(x.quantile(q)) if len(x) else None for q in (.50,.75,.90,.95,.99)}

def load_kind(kind):
    files=sorted(PART.glob(f'{kind}_*.parquet'))
    # A 100-row dry-run shard predates the real campaign and is excluded.
    files=[f for f in files if len(pd.read_parquet(f))==1000]
    d=pd.concat([pd.read_parquet(f) for f in files],ignore_index=True) if files else pd.DataFrame()
    d=d.drop_duplicates('hash',keep='first').reset_index(drop=True)
    return d

def summary(d,target):
    valid=(~d.ruin)&(d.trades>0)
    return {'target':target,'unique_evaluated':int(d.hash.nunique()),'long':int((d.direction=='LONG').sum()),'short':int((d.direction=='SHORT').sum()),'economically_valid':int(valid.sum()),'positive_return':int((d['return']>0).sum()),'positive_expectancy':int((d.economic_expectancy>0).sum()),'pf_gt_1':int((d.pf>1).sum()),'non_ruined':int((~d.ruin).sum()),'return_percentiles':quantiles(d,'return'),'expectancy_percentiles':quantiles(d,'economic_expectancy'),'pf_percentiles':quantiles(d,'pf'),'maxdd_percentiles':quantiles(d,'maxdd'),'lockbox_access':0}

def main():
    random=load_kind('random'); genetic=load_kind('genetic')
    assert len(random)==50000 and random.hash.nunique()==50000
    assert len(genetic)==200000 and genetic.hash.nunique()==200000
    random.to_parquet(OUT/'random_results.parquet',index=False)
    genetic.to_parquet(OUT/'genetic_results.parquet',index=False)
    dump('random_summary.json',summary(random,50000)); dump('genetic_summary.json',summary(genetic,200000))
    allc=pd.concat([random,genetic],ignore_index=True)
    allc.to_parquet(OUT/'all_dev_candidates.parquet',index=False)
    # Frozen profit-first DEV contract: exact economics, non-ruin, support,
    # broad internal-window participation, positive net economics, and no
    # single-window dominance. These gates are fixed before VAL access.
    gates=(~allc.ruin)&(allc.trades>=20)&(allc.active_windows>=4)&(allc.positive_window_fraction>=.50)&(allc.economic_expectancy>0)&(allc['return']>0)&(allc.pf>1)&(allc.best_window_share<=.70)
    candidates=allc[gates].copy().sort_values(['fitness','hash'],ascending=[False,True]).reset_index(drop=True)
    candidates.to_parquet(OUT/'dev_candidates_frozen.parquet',index=False)
    funnel=[]
    for label,mask in [('total',np.ones(len(allc),dtype=bool)),('economically_valid',(~allc.ruin)&(allc.trades>0)),('non_ruined',~allc.ruin),('positive_expectancy',allc.economic_expectancy>0),('positive_return',allc['return']>0),('pf_gt_1',allc.pf>1),('trade_support',allc.trades>=20),('temporal_support',(allc.active_windows>=4)&(allc.positive_window_fraction>=.50)),('profit_concentration',allc.best_window_share<=.70)]:
        funnel.append({'stage':label,'all':int(mask.sum()),'random':int((mask & (allc.kind=='RANDOM')).sum()),'genetic':int((mask & (allc.kind=='GENETIC')).sum()),'long':int((mask & (allc.direction=='LONG')).sum()),'short':int((mask & (allc.direction=='SHORT')).sum())})
    funnel.append({'stage':'final_dev_candidates','all':len(candidates),'random':int((candidates.kind=='RANDOM').sum()),'genetic':int((candidates.kind=='GENETIC').sum()),'long':int((candidates.direction=='LONG').sum()),'short':int((candidates.direction=='SHORT').sum())})
    pd.DataFrame(funnel).to_csv(OUT/'dev_candidate_funnel.csv',index=False)
    dump('dev_candidate_summary.json',{'total':len(allc),'random':summary(random,50000),'genetic':summary(genetic,200000),'final_dev_candidates':len(candidates),'final_random':int((candidates.kind=='RANDOM').sum()),'final_genetic':int((candidates.kind=='GENETIC').sum()),'gates':{'ruin':False,'trades_min':20,'active_windows_min':4,'positive_window_fraction_min':.50,'expectancy_positive':True,'return_positive':True,'pf_gt_1':True,'best_window_share_max':.70},'val_accessed':False,'oos_accessed':False,'lockbox_access':0})
    conc=candidates[['hash','kind','direction','trades','return','economic_expectancy','best_window_share','positive_window_fraction','active_windows']].copy(); conc.to_parquet(OUT/'profit_concentration.parquet',index=False)
    candidates[['hash','strategy_id','direction','trades','return','economic_expectancy','maxdd','positive_window_fraction','active_windows']].to_parquet(OUT/'behavioral_fingerprints.parquet',index=False)
    dump('random_vs_genetic.json',{'random_requested':50000,'genetic_requested':200000,'random_unique':len(random),'genetic_unique':len(genetic),'total_unique':int(allc.hash.nunique()),'random_summary':summary(random,50000),'genetic_summary':summary(genetic,200000),'final_dev_candidates':len(candidates),'val_accessed':False,'oos_accessed':False,'lockbox_access':0})
    dump('CAMPAIGN_PROGRESS.json',{'random_unique':len(random),'genetic_unique':len(genetic),'total_unique':int(allc.hash.nunique()),'status':'DEV_MANUFACTURING_COMPLETE','val_accessed':False,'oos_accessed':False,'lockbox_access':0})
    dump('CAMPAIGN_RUNTIME.json',{'random_unique':len(random),'genetic_unique':len(genetic),'total_unique':int(allc.hash.nunique()),'random_strategies_per_second':json.loads((OUT/'random_summary.json').read_text()) .get('strategies_per_second'),'genetic_strategies_per_second':json.loads((OUT/'genetic_summary.json').read_text()).get('strategies_per_second'),'status':'DEV_MANUFACTURING_COMPLETE','val_accessed':False,'oos_accessed':False,'lockbox_access':0})
    dump('PRE_VAL_FREEZE.json',{'status':'FROZEN','starting_commit':'e2f6311','code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'dataset_sha256':'f2ddfd9b85f4e7556474e1ef10f78eebd927a0f0e330785d48b4d08e5b69a20a','grammar':'v1.7 PRICE_ONLY','economic_contract':'bounded 1% current-equity heat','fitness':'profit-first frozen DEV contract','random_unique':len(random),'genetic_unique':len(genetic),'candidate_count':len(candidates),'candidate_hash':sha(OUT/'dev_candidates_frozen.parquet'),'val_accessed':False,'oos_accessed':False,'lockbox_access':0,'frozen_at_utc':pd.Timestamp.utcnow()})
    (OUT/'README.md').write_text('# Clean Reboot V1 Manufacturing\n\nDEV-only Random 50,000 and Genetic 200,000 exact bounded-economic evaluations. Candidate membership and gates are frozen here before VAL.\n')
if __name__=='__main__': main()
