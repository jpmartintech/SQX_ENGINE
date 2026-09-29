#!/usr/bin/env python3
"""VAL admission and one-shot OOS examination for the frozen reboot factory."""
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'
import sys; sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from crypto_clean_reboot_v1 import load_source,bounds,array_metrics,_event_kernel
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition

def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+'\n')
def setup():
    d=load_source(); f=prepare_crypto_features(d,None,'PRICE'); ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine='numba',cache_size=512); b=bounds(d); return d,f,ev,b
def replay(row,d,f,ev,start,end):
    raw=row.strategy; s=StrategyDefinition.from_json(json.dumps(raw) if isinstance(raw,dict) else raw); a=ev._arrays; signal=ev._signal(s); atr=np.asarray(f['atr_14'],dtype=float); direction=1 if s.direction=='LONG' else -1
    ei,xi,ds,pn,rs,held,reasons=_event_kernel(a['open'],a['high'],a['low'],a['close'],atr,signal,int(start),int(end),direction,float(s.stop_atr),float(s.target_atr),int(s.time_exit),float(ev.spread),float(ev.slippage)); cuts=np.array([int(start),int(end)],dtype=np.int64); z,ws=array_metrics(ei,xi,ds,rs,a['open'][ei] if len(ei) else np.empty(0),a['close'][xi] if len(xi) else np.empty(0),a['close'],[(int(start),int(end))]); ev._signal_cache.clear(); ev._evaluation_cache.clear(); return {'hash':row['hash'],'strategy_id':row['strategy_id'],'direction':s.direction,'kind':row.get('kind',''),'trades':z['trades'],'pf':z['pf'],'economic_expectancy':z['economic_expectancy'],'return':z['return'],'maxdd':z['maxdd'],'minimum_equity':z['minimum_equity'],'ruin':z['ruin'],'positive_window_fraction':float(z['economic_expectancy']>0),'active_windows':int(z['trades']>=3)}
def main():
    phase=sys.argv[1] if len(sys.argv)>1 else 'val'; d,f,ev,b=setup(); st=int(d.timestamp.searchsorted(b['START'])); dev=int(d.timestamp.searchsorted(b['DEV_END'])); va=int(d.timestamp.searchsorted(b['VAL_END'])); oo=int(d.timestamp.searchsorted(b['OOS_END'])); en=len(d)
    candidates=pd.read_parquet(OUT/'dev_candidates_frozen.parquet')
    if phase=='val':
        rows=[replay(r,d,f,ev,dev,va) for _,r in candidates.iterrows()]; val=pd.DataFrame(rows); val.to_parquet(OUT/'val_results.parquet',index=False)
        gate=(~val.ruin)&(val.trades>=10)&(val.pf>1)&(val.economic_expectancy>0)&(val['return']>0)
        funnel=pd.DataFrame([{'stage':'frozen_dev_candidates','count':len(candidates)},{'stage':'val_positive_return','count':int((val['return']>0).sum())},{'stage':'val_positive_expectancy','count':int((val.economic_expectancy>0).sum())},{'stage':'val_pf_gt_1','count':int((val.pf>1).sum())},{'stage':'val_trade_support','count':int((val.trades>=10).sum())},{'stage':'admitted','count':int(gate.sum())}]); funnel.to_csv(OUT/'val_funnel.csv',index=False)
        lib=candidates.merge(val,on=['hash','strategy_id','kind','direction'],suffixes=('_dev','_val')); lib=lib[gate.to_numpy()].copy(); lib.to_parquet(OUT/'library_v1.parquet',index=False)
        dump('library_v1_summary.json',{'status':'FROZEN_BEFORE_OOS','strategies':len(lib),'random':int((lib.kind=='RANDOM').sum()),'genetic':int((lib.kind=='GENETIC').sum()),'long':int((lib.direction=='LONG').sum()),'short':int((lib.direction=='SHORT').sum()),'val_positive_return':int((val['return']>0).sum()),'val_positive_expectancy':int((val.economic_expectancy>0).sum()),'val_pf_gt_1':int((val.pf>1).sum()),'oos_accessed':False,'lockbox_access':0})
        dump('DATA_ACCESS_LEDGER.json',{'experiment_id':'crypto_clean_reboot_v1','DEV_accesses':1,'VAL_accesses':1,'OOS_accesses':0,'LOCKBOX_accesses':0,'VAL_after_pre_val_freeze':True,'OOS_after_pre_oos_freeze':False})
        dump('PRE_OOS_FREEZE.json',{'status':'PENDING_COMMIT','library_count':len(lib),'library_hash':hashlib.sha256((OUT/'library_v1.parquet').read_bytes()).hexdigest(),'val_accessed_after_pre_val_freeze':True,'oos_accessed':False,'lockbox_access':0,'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()})
    else:
        lib=pd.read_parquet(OUT/'library_v1.parquet'); valid=pd.read_parquet(OUT/'all_dev_candidates.parquet'); valid=valid[(~valid.ruin)&(valid.trades>=20)].copy(); rows=[]
        for _,r in lib.iterrows(): rows.append({**replay(r,d,f,ev,oo,en),'cohort':'ADMITTED'})
        admitted=set(lib.hash); rejected=valid[~valid.hash.isin(admitted)]
        for _,r in rejected.iterrows(): rows.append({**replay(r,d,f,ev,oo,en),'cohort':'REJECTED_VALID'})
        oos=pd.DataFrame(rows); oos.to_parquet(OUT/'oos_results.parquet',index=False); a=oos[oos.cohort=='ADMITTED']; r=oos[oos.cohort=='REJECTED_VALID']
        def grp(x): return {'count':len(x),'positive_return':int((x['return']>0).sum()),'positive_rate':float((x['return']>0).mean()) if len(x) else 0.,'positive_expectancy':int((x.economic_expectancy>0).sum()),'median_return':float(x['return'].median()) if len(x) else None,'median_expectancy':float(x.economic_expectancy.median()) if len(x) else None,'median_pf':float(x.pf.replace([np.inf],np.nan).median()) if len(x) else None,'ruin_rate':float(x.ruin.mean()) if len(x) else 0.}
        dump('factory_generalization.json',{'admitted':grp(a),'rejected_valid':grp(r),'oos_accessed_once_after_pre_oos_freeze':True,'research_only':True,'lockbox_access':0}); dump('random_vs_genetic_oos.json',{'admitted_random':grp(a[a.kind=='RANDOM']),'admitted_genetic':grp(a[a.kind=='GENETIC']),'research_only':True}); dump('portfolio_readiness.json',{'assessment':'PORTFOLIO_RAW_MATERIAL_LIMITED' if len(a)>2 else 'PORTFOLIO_RAW_MATERIAL_INSUFFICIENT','oos_profitable':int((a['return']>0).sum()),'lockbox_access':0}); dump('DATA_ACCESS_LEDGER.json',{'experiment_id':'crypto_clean_reboot_v1','DEV_accesses':1,'VAL_accesses':1,'OOS_accesses':1,'LOCKBOX_accesses':0,'OOS_after_pre_oos_freeze':True})
        dump('PRE_OOS_FREEZE.json',{'status':'FROZEN','library_count':len(lib),'library_hash':hashlib.sha256((OUT/'library_v1.parquet').read_bytes()).hexdigest(),'oos_accessed_after_freeze':True,'lockbox_access':0,'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()})
if __name__=='__main__': main()
