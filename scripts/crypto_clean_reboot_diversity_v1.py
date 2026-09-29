#!/usr/bin/env python3
"""Descriptive OOS behavioral fingerprints for the frozen Library."""
from pathlib import Path
import json, numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'
import sys; sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from crypto_clean_reboot_v1 import load_source,bounds,_event_kernel
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition
def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+'\n')
def main():
    d=load_source(); f=prepare_crypto_features(d,None,'PRICE')
    ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine='numba',cache_size=512)
    b=bounds(d); a=int(d.timestamp.searchsorted(b['VAL_END'])); z=int(d.timestamp.searchsorted(b['OOS_END']))
    lib=pd.read_parquet(OUT/'library_v1.parquet').drop_duplicates('hash',keep='first').reset_index(drop=True)
    days=pd.date_range(d.timestamp.iloc[a].floor('D'),d.timestamp.iloc[z-1].floor('D'),freq='D',tz='UTC')
    daily=pd.DataFrame(0.,index=days,columns=lib.hash.astype(str))
    for _,row in lib.iterrows():
        s=StrategyDefinition.from_json(json.dumps(row.strategy) if isinstance(row.strategy,dict) else row.strategy)
        ar=ev._arrays; sig=ev._signal(s); atr=np.asarray(f['atr_14'],float); dire=1 if s.direction=='LONG' else -1
        ei,xi,ds,pn,rs,held,reasons=_event_kernel(ar['open'],ar['high'],ar['low'],ar['close'],atr,sig,a,z,dire,float(s.stop_atr),float(s.target_atr),int(s.time_exit),float(ev.spread),float(ev.slippage))
        if len(xi):
            dates=pd.DatetimeIndex(d.timestamp.iloc[xi]).floor('D'); vals=pd.Series(rs,index=dates).groupby(level=0).sum()
            daily.loc[vals.index,str(row.hash)]=vals.to_numpy()
        ev._signal_cache.clear(); ev._evaluation_cache.clear()
    weekly=daily.resample('W').sum(); x=daily.to_numpy(float); corr=np.corrcoef(x,rowvar=False); loss=np.corrcoef(np.minimum(x,0),rowvar=False); pairs=np.triu_indices_from(corr,1); dd=np.cumsum(x,axis=0); peak=np.maximum.accumulate(dd,axis=0); state=dd<peak; ov=(state.astype(float).T@state.astype(float))/len(state)
    def q(v): return {'P50':float(np.nanquantile(v,.5)),'P75':float(np.nanquantile(v,.75)),'P90':float(np.nanquantile(v,.9)),'min':float(np.nanmin(v)),'max':float(np.nanmax(v))}
    dump('behavioral_correlation_summary.json',{'daily':q(corr[pairs]),'weekly':q(np.corrcoef(weekly.to_numpy(float),rowvar=False)[pairs]),'downside':q(loss[pairs]),'drawdown_overlap':q(ov[pairs]),'pairs':int(len(pairs[0])),'method':'aligned incremental exit-R series; zero-no-trade periods are zero; descriptive only','lockbox_access':0})
    daily.reset_index(names='timestamp').to_parquet(OUT/'daily_pnl_matrix.parquet'); weekly.reset_index(names='timestamp').to_parquet(OUT/'weekly_pnl_matrix.parquet')
if __name__=='__main__': main()
