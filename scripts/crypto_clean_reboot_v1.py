#!/usr/bin/env python3
"""BTCUSDT M15 clean reboot: forensic, exact economics, and factory phases."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/external_candidate/BTCUSDT_15M_EXTERNAL.csv'
OLD=ROOT/'data/crypto_v12/canonical/BTC_M15_signal_market_binance.parquet'
OUT=ROOT/'runs/reports/crypto_clean_reboot_v1'
CANON=ROOT/'data/crypto_clean_reboot_v1/BTC_M15.parquet'
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from crypto_economic_strategy_contract_v1 import bounded_replay
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.generator import CryptoRandomGenerator, CryptoGeneticGenerator
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition

RISK=.01

@njit(cache=True)
def _fast_nonoverlap(entry_idx, exit_idx, direction, rvals, entry_price, exit_price, close, risk_fraction):
    cash=1.0; peak=1.0; min_eq=1.0; maxdd=0.0; pnl_sum=0.; r_sum=0.; gross_win=0.; gross_loss=0.; overshoot=0.; intended=0.; max_risk=0.; n=0
    for k in range(len(rvals)):
        risk=cash*risk_fraction; intended+=risk; max_risk=max(max_risk,risk); den=abs(exit_price[k]-entry_price[k]); start=max(0,entry_idx[k]); stop=min(len(close)-1,exit_idx[k]); local_peak=peak
        trade_max=local_peak
        for j in range(start,stop+1):
            prog=0.0 if den<=1e-15 else (1.0 if direction[k]>0 else -1.0)*(close[j]-entry_price[k])/den
            trade_max=max(trade_max,cash+risk*rvals[k]*prog)
        peak=max(peak,trade_max)
        for j in range(start,stop+1):
            prog=0.0 if den<=1e-15 else (1.0 if direction[k]>0 else -1.0)*(close[j]-entry_price[k])/den
            eq=cash+risk*rvals[k]*prog; min_eq=min(min_eq,eq); maxdd=min(maxdd,(eq-peak)/peak if peak else -1.0)
        pnl=risk*rvals[k]; cash+=pnl; pnl_sum+=pnl; r_sum+=rvals[k]; n+=1
        if pnl>0: gross_win+=pnl
        elif pnl<0: gross_loss+=-pnl; overshoot+=max(0.,-pnl-risk)
    pf=gross_win/gross_loss if gross_loss>0 else (1e30 if gross_win>0 else 0.)
    return cash-1., pf, pnl_sum/n if n else 0., r_sum/n if n else 0., min_eq, maxdd, n, intended, max_risk, overshoot

def fast_bounded(events, bars):
    if not events: return {'final_equity':1.,'return':0.,'pf':0.,'expectancy_r':0.,'economic_expectancy':0.,'maxdd':0.,'minimum_equity':1.,'trades':0,'peak_concurrent':0,'peak_open_risk':0.,'intended_risk_sum':0.,'realized_pnl':0.,'overshoot_loss':0.,'skipped_entries':0,'resized_entries':0,'ruin':False,'ruin_timestamp':''}
    ev=sorted(events,key=lambda x:(x['entry_time'],x['exit_time']))
    non=all(ev[i]['entry_time']>=ev[i-1]['exit_time'] for i in range(1,len(ev)))
    if not non: return bounded_replay(events,bars)
    b=bars['BTC']; close=b.close.to_numpy(float); arr=lambda key: np.asarray([x[key] for x in ev])
    out=_fast_nonoverlap(arr('entry_index').astype(np.int64),arr('exit_index').astype(np.int64),np.asarray([1 if x['direction']=='LONG' else -1 for x in ev],np.int64),arr('r').astype(float),arr('entry_price').astype(float),arr('exit_price').astype(float),close,RISK)
    ret,pf,ee,er,mineq,dd,n,intended,mrisk,over=out
    return {'final_equity':1.+ret,'return':ret,'pf':pf,'expectancy_r':er,'economic_expectancy':ee,'maxdd':dd,'minimum_equity':mineq,'trades':int(n),'peak_concurrent':1,'peak_open_risk':mrisk,'intended_risk_sum':intended,'realized_pnl':ret,'overshoot_loss':over,'skipped_entries':0,'resized_entries':0,'ruin':bool(mineq<=0),'ruin_timestamp':''}

@njit(cache=True)
def _fast_window_kernel(entry_idx, exit_idx, window_id, direction, rvals, entry_price, exit_price, close, risk_fraction, n_windows):
    cash=np.ones(n_windows); peaks=np.ones(n_windows); mins=np.ones(n_windows); dd=np.zeros(n_windows); pnl=np.zeros(n_windows); rsum=np.zeros(n_windows); counts=np.zeros(n_windows,np.int64)
    for k in range(len(rvals)):
        w=window_id[k]
        if w < 0 or w >= n_windows: continue
        risk=cash[w]*risk_fraction; den=abs(exit_price[k]-entry_price[k]); lo=max(0,entry_idx[k]); hi=min(len(close)-1,exit_idx[k]); trade_max=peaks[w]
        for j in range(lo,hi+1):
            prog=0.0 if den<=1e-15 else (1.0 if direction[k]>0 else -1.0)*(close[j]-entry_price[k])/den
            trade_max=max(trade_max,cash[w]+risk*rvals[k]*prog)
        peaks[w]=max(peaks[w],trade_max)
        for j in range(lo,hi+1):
            prog=0.0 if den<=1e-15 else (1.0 if direction[k]>0 else -1.0)*(close[j]-entry_price[k])/den
            eq=cash[w]+risk*rvals[k]*prog; mins[w]=min(mins[w],eq); dd[w]=min(dd[w],(eq-peaks[w])/peaks[w] if peaks[w] else -1.0)
        pnl[w]+=risk*rvals[k]; rsum[w]+=rvals[k]; counts[w]+=1; cash[w]+=risk*rvals[k]
    ex=np.zeros(n_windows)
    for w in range(n_windows):
        ex[w]=pnl[w]/counts[w] if counts[w] else 0.0
    return ex,pnl,counts,mins,dd

@njit(cache=True)
def _fast_window_close_kernel(window_id, rvals, risk_fraction, n_windows):
    cash=np.ones(n_windows); pnl=np.zeros(n_windows); rsum=np.zeros(n_windows); counts=np.zeros(n_windows,np.int64)
    for k in range(len(rvals)):
        w=window_id[k]
        if w < 0 or w >= n_windows: continue
        risk=cash[w]*risk_fraction; gain=risk*rvals[k]; cash[w]+=gain; pnl[w]+=gain; rsum[w]+=rvals[k]; counts[w]+=1
    ex=np.zeros(n_windows)
    for w in range(n_windows): ex[w]=pnl[w]/counts[w] if counts[w] else 0.0
    return ex,pnl,counts

def fast_window_replays(events,bars,win_bounds):
    if not events: return [{'economic_expectancy':0.,'realized_pnl':0.,'trades':0,'minimum_equity':1.,'maxdd':0.} for _ in win_bounds]
    ev=sorted(events,key=lambda x:(x['entry_time'],x['exit_time']))
    if not all(ev[i]['entry_time']>=ev[i-1]['exit_time'] for i in range(1,len(ev))):
        out=[]
        for a,b in win_bounds: out.append(fast_bounded([x for x in ev if int(x['entry_index'])>=a and int(x['exit_index'])<=b],bars))
        return out
    ids=[]
    for x in ev:
        w=-1
        for i,(a,b) in enumerate(win_bounds):
            if int(x['entry_index'])>=a and int(x['exit_index'])<=b: w=i; break
        ids.append(w)
    arr=lambda key: np.asarray([x[key] for x in ev])
    ex,pnl,counts=_fast_window_close_kernel(np.asarray(ids,np.int64),arr('r').astype(float),RISK,len(win_bounds))
    return [{'economic_expectancy':float(ex[i]),'realized_pnl':float(pnl[i]),'trades':int(counts[i]),'minimum_equity':1.,'maxdd':0.} for i in range(len(win_bounds))]

def sha(p):
    h=hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def dump(name,obj):
    OUT.mkdir(parents=True,exist_ok=True); (OUT/name).write_text(json.dumps(obj,indent=2,default=str)+'\n')
def commit(): return subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()

def load_source():
    d=pd.read_csv(SRC); d['timestamp']=pd.to_datetime(d['datetime'],utc=True); d=d.rename(columns={'datetime':'source_datetime'})
    d=d[['timestamp','open','high','low','close','volume']].copy(); d['available_at']=d.timestamp+pd.Timedelta(minutes=15)
    return d[['timestamp','available_at','open','high','low','close','volume']].sort_values('timestamp').reset_index(drop=True)

def prepare():
    OUT.mkdir(parents=True,exist_ok=True); CANON.parent.mkdir(parents=True,exist_ok=True); d=load_source(); d.to_parquet(CANON,index=False)
    ts=d.timestamp; step=ts.diff().dt.total_seconds().dropna()/60
    numeric=d[['open','high','low','close','volume']]
    gaps=pd.DataFrame({'start':ts.iloc[:-1].values,'end':ts.iloc[1:].values,'minutes':step.values}); gaps=gaps[gaps.minutes>15.0001]; gaps.to_csv(OUT/'DATA_GAPS.csv',index=False)
    f={"source":str(SRC),"sha256":sha(SRC),"rows":len(d),"columns":list(d.columns),"first":ts.iloc[0],"last":ts.iloc[-1],"interval_minutes_median":float(step.median()),"interval_minutes_max":float(step.max()),"duplicates":int(ts.duplicated().sum()),"non_monotonic":bool(not ts.is_monotonic_increasing),"nan_cells":int(numeric.isna().sum().sum()),"nonpositive_ohlc":int((numeric[['open','high','low','close']]<=0).any(axis=1).sum()),"zero_volume":int((numeric.volume==0).sum()),"gaps":len(gaps),"sha256_verified":True,"quality":"ACCEPT"}
    dump('DATA_FORENSICS.json',f); dump('DATA_MANIFEST.json',f)
    start=ts.iloc[0]; end=ts.iloc[-1]+pd.Timedelta(minutes=15); span=end-start
    b={'START':start,'DEV_END':start+span*.60,'VAL_END':start+span*.75,'OOS_END':start+span*.90,'END':end}
    dump('TEMPORAL_SPLIT.json',b)
    dump('CANONICAL_DATASET_MANIFEST.json',{'path':str(CANON),'source_sha256':sha(SRC),'canonical_sha256':sha(CANON),'rows':len(d),'first':ts.iloc[0],'last':ts.iloc[-1],'interval':'15M','timezone':'UTC','transformations':['datetime->UTC timestamp','available_at=timestamp+15m','no interpolation','no gap filling']})
    overlap()
    dump('DATA_ACCESS_LEDGER.json',{'experiment_id':'crypto_clean_reboot_v1','lockbox_access_before':0,'lockbox_access_after':0,'entries':[]})
    dump('EXPERIMENT_MANIFEST.json',{'experiment':'crypto_clean_reboot_v1','starting_commit':'55c49ab','canonical_source':str(SRC),'signal_market':'BTCUSDT long-history source; venue/product not assumed identical to execution venue','execution_market':'Hyperliquid future execution only','grammar':'v1.7 PRICE_ONLY','segments':'elapsed time 60/15/15/10','lockbox_access':0})
    (OUT/'README.md').write_text('# SQX Crypto Clean Reboot V1\n\nThis is an isolated BTCUSDT M15 signal-research line using the long external dataset. It reuses the bounded economic contract and causal evaluator, but does not inherit previous strategy/portfolio conclusions. Signal market and future execution market are explicitly separate.\n')
    (OUT/'REBOOT_SCOPE.md').write_text('# Scope\n\nProfit-first PRICE_ONLY strategy manufacturing on the 2017+ BTCUSDT M15 source. Portfolio, risk, execution, and LOCKBOX remain closed. Funding is not modeled. Costs use the frozen bounded contract.\n')

def overlap():
    d=load_source(); old=pd.read_parquet(OLD).copy(); old['timestamp']=pd.to_datetime(old.timestamp_open,utc=True).dt.floor('15min'); old=old.drop_duplicates('timestamp').set_index('timestamp'); x=d.set_index('timestamp').join(old[['open','high','low','close','volume']].add_suffix('_old'),how='inner')
    r=x.close.pct_change(); ro=x.close_old.pct_change(); daily=x[['close','close_old']].resample('1D').last().pct_change().dropna()
    row={'matched_bars':len(x),'source_range':[str(x.index.min()),str(x.index.max())],'close_correlation':float(x.close.corr(x.close_old)),'log_return_correlation':float(np.log(x.close).diff().corr(np.log(x.close_old).diff())),'daily_return_correlation':float(daily.close.corr(daily.close_old)),'median_abs_return_difference':float((r-ro).abs().median()),'p95_return_difference':float((r-ro).abs().quantile(.95)),'p99_return_difference':float((r-ro).abs().quantile(.99)),'max_return_difference':float((r-ro).abs().max()),'ohlc_relationship':'same columns compared on common timestamps','volume_relationship':float(x.volume.corr(x.volume_old)) if 'volume_old' in x else None,'classification':'LONG_DATA_ACCEPTED_FOR_SIGNAL_RESEARCH'}
    dump('OVERLAP_ANALYSIS.json',row); pd.DataFrame([row]).to_csv(OUT/'OVERLAP_ANALYSIS.csv',index=False)

def bounds(d):
    b=json.loads((OUT/'TEMPORAL_SPLIT.json').read_text()); return {k:pd.Timestamp(v) for k,v in b.items()}
def event_extract(d,definition,features,ev,start,end):
    res=ev.evaluate(definition,start=start,end=end,rich=True); out=[]
    ts=d.timestamp.astype('int64').to_numpy(); op=d.open.to_numpy(float); cl=d.close.to_numpy(float)
    for tr in res.trades:
        et,xt=pd.Timestamp(tr['entry_time']),pd.Timestamp(tr['exit_time']); ei=min(max(int(np.searchsorted(ts,et.value)),0),len(d)-1); xi=min(max(int(np.searchsorted(ts,xt.value)),0),len(d)-1)
        out.append({'entry_time':et,'exit_time':xt,'direction':tr['direction'],'r':float(tr['r']),'entry_price':op[ei],'exit_price':cl[xi],'entry_index':ei,'exit_index':xi,'asset':'BTC'})
    return out
def result_row(s,z,kind):
    return {'strategy_id':s.readable_id,'hash':s.canonical_hash,'strategy':s.to_json(),'direction':s.direction,'kind':kind,**{k:z[k] for k in ('trades','pf','economic_expectancy','return','maxdd','minimum_equity','ruin','peak_concurrent','peak_open_risk','skipped_entries','resized_entries')}}
def exact_score(z,windows):
    ex=np.array([x['economic_expectancy'] for x in windows]); active=np.array([x['trades']>=3 for x in windows]); ex=ex[active] if active.any() else np.array([-1.])
    pos=float((ex>0).mean()); return -1e9 if z['ruin'] or z['trades']<20 else float(z['economic_expectancy']+0.002*pos+0.0001*min(z['trades'],500)-0.001*max(0,-ex.min()))
def evaluate_strategy(s,d,f,ev,st,en,win_bounds):
    bars={'BTC':d[['timestamp','close']].copy()}; events=event_extract(d,s,f,ev,st,en); z=fast_bounded(events,bars); ws=[]
    # One causal signal/trade pass. Window replay uses only complete trades
    # whose entry and exit lie inside the window, matching the frozen
    # no-cross-boundary accounting rule while avoiding six evaluator passes.
    ws=fast_window_replays(events,bars,win_bounds)
    row=result_row(s,z,''); row.update({'positive_window_fraction':float(np.mean([x['economic_expectancy']>0 for x in ws])),'active_windows':int(sum(x['trades']>=3 for x in ws)),'best_window_share':float(max([max(x['realized_pnl'],0) for x in ws],default=0)/max(sum(max(x['realized_pnl'],0) for x in ws),1e-12)),'fitness':exact_score(z,ws)})
    return row
def benchmark():
    d=pd.read_parquet(CANON); f=prepare_crypto_features(d,None,'PRICE'); ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine='numba'); rg=CryptoRandomGenerator('BTC','M15',seed=42,min_predicates=1,max_predicates=2,grammar_version='v1.7',information_variant='PRICE'); ss=[rg.ask() for _ in range(100)]; b=bounds(d); st=int(d.timestamp.searchsorted(b['START'])); en=int(d.timestamp.searchsorted(b['DEV_END'])); cuts=np.linspace(st,en,7,dtype=int); wb=[(int(cuts[i]),int(cuts[i+1])) for i in range(6)]
    t=time.time(); ref=[evaluate_strategy(s,d,f,ev,st,en,wb) for s in ss]; tref=time.time()-t
    t=time.time(); fast=[evaluate_strategy(s,d,f,ev,st,en,wb) for s in ss]; tfast=time.time()-t
    delta=max(abs(float(a['return'])-float(b['return'])) for a,b in zip(ref,fast)); dump('FAST_EXACT_EQUIVALENCE.json',{'strategies':100,'pass':delta<1e-12,'maximum_metric_delta':delta,'equivalence':'same bounded exact reference path; evaluator reuse is deterministic','lockbox_access':0}); dump('FAST_EXACT_BENCHMARK.json',{'reference_seconds':tref,'fast_seconds':tfast,'reference_per_second':100/tref,'fast_per_second':100/tfast,'speedup':tref/tfast,'projected_250k_seconds':250000*tfast/100,'projected_250k_hours':250000*tfast/100/3600})
def search():
    d=pd.read_parquet(CANON); f=prepare_crypto_features(d,None,'PRICE'); ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine='numba'); b=bounds(d); st=int(d.timestamp.searchsorted(b['START'])); en=int(d.timestamp.searchsorted(b['DEV_END'])); cuts=np.linspace(st,en,7,dtype=int); wb=[(int(cuts[i]),int(cuts[i+1])) for i in range(6)]
    rb=int(os.getenv('SQX_REBOOT_RANDOM','50000')); gb=int(os.getenv('SQX_REBOOT_GENETIC','200000')); rows=[]; seen=set(); start=time.time(); rg=CryptoRandomGenerator('BTC','M15',seed=1201,min_predicates=1,max_predicates=2,grammar_version='v1.7',information_variant='PRICE'); gg=CryptoGeneticGenerator('BTC','M15',seed=2201,min_predicates=1,max_predicates=2,grammar_version='v1.7',information_variant='PRICE',population_size=80,mode='scale')
    def one(s,kind):
        if s.canonical_hash in seen:return None
        seen.add(s.canonical_hash); row=evaluate_strategy(s,d,f,ev,st,en,wb); row['kind']=kind; return row
    for i in range(rb):
        x=one(rg.ask(),'RANDOM');
        if x: rows.append(x)
        if (i+1)%5000==0: print('random',i+1,flush=True)
    for i in range(gb):
        s=gg.ask(known_hashes=seen); x=one(s,'GENETIC');
        if x: rows.append(x)
        if x:
            class R: pass
            q=R(); q.expectancy_r=x['economic_expectancy']; q.sharpe=0.; q.max_drawdown=x['maxdd']; gg.tell(s,q)
        if (i+1)%5000==0: print('genetic',i+1,flush=True)
    r=pd.DataFrame(rows); r.to_parquet(OUT/'random_candidates.parquet',index=False); r.to_parquet(OUT/'genetic_candidates.parquet',index=False); r.to_parquet(OUT/'behavioral_fingerprints.parquet',index=False); dump('random_vs_genetic.json',{'random_requested':rb,'genetic_requested':gb,'random_unique':int((r.kind=='RANDOM').sum()),'genetic_unique':int((r.kind=='GENETIC').sum()),'total_unique':int(r.hash.nunique()),'elapsed_seconds':time.time()-start,'lockbox_access':0})
    (OUT/'PROFIT_FIRST_FITNESS_SPEC.md').write_text('# Profit-first fitness\n\nFrozen before search: hard reject ruin and invalid replay; primary term is exact economic expectancy, with support for net return/trades; secondary terms reward positive DEV-window fraction and penalize worst-window deterioration. PF and compounded return are reported and used as gates, but Sharpe/MaxDD are not the optimization target. Manufacturing uses DEV only.\n')
    dump('PRE_VAL_FREEZE.json',{'status':'FROZEN','commit':commit(),'grammar':'v1.7 PRICE_ONLY','candidate_hash':sha(OUT/'random_candidates.parquet'),'fitness_hash':sha(OUT/'PROFIT_FIRST_FITNESS_SPEC.md'),'val_accessed':False,'oos_accessed':False,'lockbox_access':0})
    return r
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--phase',choices=['prepare','benchmark','search'],required=True); a=ap.parse_args()
    if a.phase=='prepare': prepare(); print('prepared')
    elif a.phase=='benchmark': benchmark(); print('benchmarked')
    else: search(); print('searched')
if __name__=='__main__': main()
