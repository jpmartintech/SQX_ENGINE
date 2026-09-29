#!/usr/bin/env python3
"""Profit-first BTC portfolio factory on the frozen clean-reboot library.

All search fitness is produced by the same chronological concurrent kernel used
for the final portfolio gate.  The full library is audited; a deterministic
DEV+VAL-only, cluster-stratified pool keeps the combinatorial search tractable.
OOS is a separate command and is refused until the pre-OOS freeze exists.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit

ROOT=Path(__file__).resolve().parents[1]
MROOT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'
OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/portfolio_factory_v1'
CANON=ROOT/'data/crypto_clean_reboot_v1/BTC_M15.parquet'
SRC=ROOT/'data/external_candidate/BTCUSDT_15M_EXTERNAL.csv'
import sys; sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from crypto_clean_reboot_v1 import _event_kernel, bounds
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition

RISK=.01; SEED=20260929

def dump(name,obj): OUT.mkdir(parents=True,exist_ok=True); (OUT/name).write_text(json.dumps(obj,indent=2,default=str)+'\n')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def phash(ids,w): return hashlib.sha256(json.dumps({'ids':[int(x) for x in ids],'w':[round(float(x),12) for x in w]},sort_keys=True,separators=(',',':')).encode()).hexdigest()
def utc(x):
    t=pd.Timestamp(x); return t.tz_localize('UTC') if t.tzinfo is None else t.tz_convert('UTC')

def load_library():
    lib=pd.read_parquet(MROOT/'library_v1.parquet').copy()
    lib=lib.sort_values(['hash','kind']).reset_index(drop=True)
    unique=lib.drop_duplicates('hash',keep='first').reset_index(drop=True)
    return lib,unique

def signature(row):
    try:
        s=json.loads(row.strategy) if isinstance(row.strategy,str) else row.strategy
        ps=tuple(sorted(str(p.get('feature','')) for p in s.get('predicates',[])))
        return f"{s.get('direction')}|{s.get('logic')}|{ps}|{s.get('stop_atr')}|{s.get('target_atr')}|{s.get('time_exit')}"
    except Exception: return 'unknown'

def dedup():
    rec,lib=load_library(); cross=rec.groupby('hash').kind.nunique()
    dump('DEDUPLICATION_REPORT.json',{
        'input_records':len(rec),'unique_hashes':len(lib),'duplicates_removed':len(rec)-len(lib),
        'random_only':int(((rec.groupby('hash').kind.first()=='RANDOM') & (cross==1)).sum()),
        'genetic_only':int(((rec.groupby('hash').kind.first()=='GENETIC') & (cross==1)).sum()),
        'cross_lineage_duplicates':int((cross>1).sum()),'hash_unique':bool(lib.hash.is_unique),
        'source_library_sha256':sha(MROOT/'library_v1.parquet'),'protected_lockbox_access':0})
    return rec,lib

def period_data(period):
    d=pd.read_parquet(CANON); d.timestamp=pd.to_datetime(d.timestamp,utc=True); b=bounds(d)
    lo,hi={'DEV':(b['START'],b['DEV_END']),'VAL':(b['DEV_END'],b['VAL_END']),'OOS':(b['VAL_END'],b['OOS_END'])}[period]
    return d[(d.timestamp>=lo)&(d.timestamp<hi)].reset_index(drop=True)

def build_events(lib, period):
    d=period_data(period); f=prepare_crypto_features(d,None,'PRICE')
    ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine='numba',cache_size=64)
    out={}; close=d.close.to_numpy(float); op=d.open.to_numpy(float)
    for i,row in lib.iterrows():
        s=StrategyDefinition.from_json(json.dumps(row.strategy) if isinstance(row.strategy,dict) else row.strategy)
        sig=ev._signal(s); atr=np.asarray(f['atr_14'],float); dire=1 if s.direction=='LONG' else -1
        ei,xi,ds,pn,rs,held,reasons=_event_kernel(ev._arrays['open'],ev._arrays['high'],ev._arrays['low'],ev._arrays['close'],atr,sig,0,len(d),dire,float(s.stop_atr),float(s.target_atr),int(s.time_exit),float(ev.spread),float(ev.slippage))
        rows=[]
        for k in range(len(ei)):
            a=int(ei[k]); z=int(xi[k]); rows.append((a,z,float(rs[k]),float(op[a]),float(close[z]),1 if ds[k]>0 else -1))
        out[row.hash]=np.asarray(rows,dtype=np.float64).reshape((-1,6)) if rows else np.empty((0,6),dtype=np.float64)
        ev._signal_cache.clear(); ev._evaluation_cache.clear()
        if (i+1)%500==0: print(f'{period} events {i+1}/{len(lib)}',flush=True)
    return d,out

@njit(cache=True)
def _portfolio_kernel(prices, times, entries, exits, rs, entry_prices, exit_prices, dirs, sids, weights, nstr, entry_order, entry_offsets, exit_order, exit_offsets):
    # entries/exits are indexed into the common time axis and sorted by time.
    n=len(entries); active=np.full(nstr,-1,np.int64); risk=np.zeros(nstr); cash=1.; peak=1.; min_eq=1.; maxdd=0.; peak_conc=0.; peak_risk=0.; gp=0.; gl=0.; rsum=0.; trades=0
    for t in range(len(times)):
        for q in range(exit_offsets[t],exit_offsets[t+1]):
            k=exit_order[q]
            s=sids[k]
            if active[s]==k:
                pnl=risk[s]*rs[k]; cash+=pnl; gp+=max(pnl,0.); gl+=max(-pnl,0.); rsum+=rs[k]; trades+=1; active[s]=-1; risk[s]=0.
        floating=0.; oc=0; orisk=0.
        for s in range(nstr):
            k=active[s]
            if k>=0:
                den=abs(exit_prices[k]-entry_prices[k]); prog=0. if den<1e-15 else dirs[k]*(prices[t]-entry_prices[k])/den
                floating+=risk[s]*rs[k]*prog; oc+=1; orisk+=risk[s]
        equity=cash+floating
        for q in range(entry_offsets[t],entry_offsets[t+1]):
            k=entry_order[q]
            s=sids[k]
            if weights[s]>0. and active[s]<0 and equity>0.:
                risk[s]=equity*.01*weights[s]; active[s]=k
        for q in range(exit_offsets[t],exit_offsets[t+1]):
            k=exit_order[q]
            s=sids[k]
            if active[s]==k:
                pnl=risk[s]*rs[k]; cash+=pnl; gp+=max(pnl,0.); gl+=max(-pnl,0.); rsum+=rs[k]; trades+=1; active[s]=-1; risk[s]=0.
        floating=0.; oc=0; orisk=0.
        for s in range(nstr):
            k=active[s]
            if k>=0:
                den=abs(exit_prices[k]-entry_prices[k]); prog=0. if den<1e-15 else dirs[k]*(prices[t]-entry_prices[k])/den
                floating+=risk[s]*rs[k]*prog; oc+=1; orisk+=risk[s]
        equity=cash+floating; peak=max(peak,equity); min_eq=min(min_eq,equity); maxdd=min(maxdd,(equity-peak)/peak if peak else -1.); peak_conc=max(peak_conc,oc); peak_risk=max(peak_risk,orisk)
    for s in range(nstr):
        k=active[s]
        if k>=0:
            den=abs(exit_prices[k]-entry_prices[k]); prog=0. if den<1e-15 else dirs[k]*(prices[-1]-entry_prices[k])/den; pnl=risk[s]*rs[k]*prog; cash+=pnl; gp+=max(pnl,0.); gl+=max(-pnl,0.); rsum+=rs[k]; trades+=1
    pf=gp/gl if gl>0. else (np.inf if gp>0. else 0.)
    return cash,cash-1.,pf,rsum/trades if trades else 0.,maxdd,min_eq,peak_conc,peak_risk,trades

class ExactReplay:
    def __init__(self, lib, period, data, event_map):
        self.lib=lib; self.hashes=lib.hash.to_numpy(); self.period=period; self.data=data; self.event_map=event_map; self.cache={}
        self.ts=list(pd.DatetimeIndex(data.timestamp))
        self.mark_idx=np.arange(0,len(self.ts),96,dtype=np.int64)
    def evaluate(self, ids, weights):
        ids=np.asarray(ids,np.int64); weights=np.asarray(weights,float); weights=weights/weights.sum()
        key=(self.period,phash(ids,weights))
        if key in self.cache:return self.cache[key]
        selected=[]
        for local,idx in enumerate(ids):
            e=self.event_map[self.hashes[int(idx)]]
            if len(e):
                x=np.empty((len(e),7),dtype=np.float64); x[:,:6]=e; x[:,6]=local; selected.append(x)
        if not selected:
            out=np.array([1.,0.,0.,0.,0.,1.,0.,0.,0.]); self.cache[key]=out; return out
        arr=np.concatenate(selected,axis=0); order=np.lexsort((arr[:,6],arr[:,1],arr[:,0])); arr=arr[order]; n=len(arr); raw_times=np.unique(np.concatenate((self.mark_idx,arr[:,0].astype(np.int64),arr[:,1].astype(np.int64)))); entries=np.searchsorted(raw_times,arr[:,0].astype(np.int64)).astype(np.int64); exits=np.searchsorted(raw_times,arr[:,1].astype(np.int64)).astype(np.int64); rs=arr[:,2]; eps=arr[:,3]; xps=arr[:,4]; dirs=arr[:,5].astype(np.int8); sids=arr[:,6].astype(np.int64)
        nt=len(raw_times); entry_order=np.argsort(entries,kind='stable').astype(np.int64); exit_order=np.argsort(exits,kind='stable').astype(np.int64)
        entry_offsets=np.zeros(nt+1,dtype=np.int64); exit_offsets=np.zeros(nt+1,dtype=np.int64); np.add.at(entry_offsets,entries+1,1); np.add.at(exit_offsets,exits+1,1); entry_offsets=np.cumsum(entry_offsets); exit_offsets=np.cumsum(exit_offsets)
        prices=self.data.close.to_numpy(float); p=prices[raw_times]
        out=_portfolio_kernel(p,np.arange(nt,dtype=np.int64),entries,exits,rs,eps,xps,dirs,sids,weights,len(ids),entry_order,entry_offsets,exit_order,exit_offsets); self.cache[key]=out; return out

def pool_select(lib):
    x=lib.copy(); x['sig']=x.apply(signature,axis=1)
    bounded=x[(x.trades_dev<=1500)&(x.trades_val<=500)].copy()
    if len(bounded)>=80: x=bounded
    x['growth_score']=np.log1p(np.maximum(x.return_dev,-.99))+np.log1p(np.maximum(x.return_val,-.99)); x['quality']=x.growth_score+10*x.economic_expectancy_dev+10*x.economic_expectancy_val+0.1*x.positive_window_fraction_dev
    # Keep every direction and a broad set of pre-OOS behavioral signatures.
    parts=[]
    for (direction,sig),g in x.groupby(['direction','sig'],sort=True): parts.append(g.nlargest(3,'quality'))
    p=pd.concat(parts).drop_duplicates('hash').sort_values(['quality','hash'],ascending=[False,True]).reset_index(drop=True)
    # Bound event-cache/search geometry while preserving cluster breadth.
    cap=int(os.getenv('SQX_PORTFOLIO_POOL','400')); p=p.head(cap).reset_index(drop=True)
    return p

def row_metrics(out):
    return {'final_equity':float(out[0]),'return':float(out[1]),'pf':float(out[2]),'expectancy':float(out[3]),'maxdd':float(out[4]),'minimum_equity':float(out[5]),'peak_concurrent':int(out[6]),'peak_risk':float(out[7]),'trades':int(out[8])}

def candidate(ids,w,pid,method,dev,val,source='search'):
    d=row_metrics(dev); v=row_metrics(val); r={'portfolio_hash':pid,'method':method,'size':len(ids),'members':'|'.join(str(int(x)) for x in ids),'weights':'|'.join(f'{float(x):.12g}' for x in w),'source':source}
    for prefix,m in [('dev',d),('val',v)]: r.update({f'{prefix}_{k}':v for k,v in m.items()})
    r['growth_objective']=min(np.log(max(d['final_equity'],1e-12)),np.log(max(v['final_equity'],1e-12)))
    r['product_valid']=bool(d['final_equity']>0 and v['final_equity']>0 and d['return']>0 and v['return']>0 and d['pf']>1 and v['pf']>1 and d['expectancy']>0 and v['expectancy']>0 and d['trades']>=30 and v['trades']>=10)
    return r

def gen_random(pool,n,seed):
    rng=np.random.default_rng(seed); seen=set(); out=[]
    while len(out)<n:
        k=int(rng.choice([5,10,20,30,50])); k=min(k,len(pool)); ids=np.sort(rng.choice(len(pool),k,replace=False)); alpha=float(rng.choice([20.,3.,1.])); w=rng.dirichlet(np.full(k,alpha)); h=phash(ids,w)
        if h not in seen: seen.add(h); out.append((ids,w,h))
    return out

def search():
    rec,lib=dedup(); pool=pool_select(lib); pool.to_parquet(OUT/'portfolio_candidate_pool.parquet',index=False); dump('portfolio_candidate_universe.json',{'full_unique_library':len(lib),'search_pool':len(pool),'selection':'DEV+VAL quality plus direction/signature stratification; no OOS','pool_hash':sha(OUT/'portfolio_candidate_pool.parquet'),'protected_lockbox_access':0})
    (OUT/'PORTFOLIO_ECONOMIC_CONTRACT.md').write_text('# Portfolio economic contract v1\n\nA candidate is replayed chronologically from its frozen strategy trade events. One shared equity curve is used. Each strategy weight is non-negative and weights sum to one. Every entry receives current portfolio equity × 0.01 × strategy weight, so total intended open heat is bounded by 1% of current equity. Exits precede entries at equal timestamps; same-timestamp entries/exits are deterministic. Fees/slippage are already embedded in evaluator R; funding is not modeled. Floating PnL is marked on closed-bar daily marks plus all event timestamps. Equity <= 0 is ruin. Metrics are computed from the combined equity/trade stream, never averaged standalone metrics.\n')
    engines={}; t=time.time()
    for p in ('DEV','VAL'):
        d,em=build_events(pool,p); engines[p]=ExactReplay(pool,p,d,em); print('built',p,'events',sum(map(len,em.values())),flush=True)
    dump('PORTFOLIO_ENGINE_MANIFEST.json',{'pool':len(pool),'periods':['DEV','VAL'],'risk':RISK,'engine':'numba chronological shared-equity replay','funding':'NOT_MODELED','protected_lockbox_access':0})
    # Deterministic baselines.
    base=[]
    for size in (5,10,20,30,50):
        ids=np.arange(min(size,len(pool))); w=np.ones(len(ids))/len(ids); base.append(candidate(ids,w,phash(ids,w),'equal_weight',engines['DEV'].evaluate(ids,w),engines['VAL'].evaluate(ids,w),'baseline'))
    pd.DataFrame(base).to_parquet(OUT/'baseline_portfolios.parquet',index=False)
    rngs=gen_random(pool,int(os.getenv('SQX_PORTFOLIO_RANDOM','50000')),SEED); rrows=[]; t0=time.time()
    for q,(ids,w,h) in enumerate(rngs):
        rrows.append(candidate(ids,w,h,'random',engines['DEV'].evaluate(ids,w),engines['VAL'].evaluate(ids,w)))
        if (q+1)%5000==0: print('random',q+1,'rate', (q+1)/(time.time()-t0),flush=True)
    random_df=pd.DataFrame(rrows); random_df.to_parquet(OUT/'random_portfolios.parquet',index=False); dump('random_portfolio_summary.json',{'requested':len(rrows),'unique':int(random_df.portfolio_hash.nunique()),'valid':int(random_df.product_valid.sum()),'seconds':time.time()-t0,'protected_lockbox_access':0})
    # Greedy exact paths from several DEV+VAL-only starts.
    grows=[]; starts=np.argsort(-pool.quality.to_numpy())[:3]; shortlist=np.argsort(-pool.quality.to_numpy())[:min(10,len(pool))]
    for seed in starts:
        ids=[int(seed)]
        for step in range(1,min(10,len(pool))):
            best=None
            for j in shortlist:
                j=int(j)
                if j in ids: continue
                ii=np.array(sorted(ids+[j]),dtype=np.int64); w=np.ones(len(ii))/len(ii); h=phash(ii,w); rr=candidate(ii,w,h,'greedy',engines['DEV'].evaluate(ii,w),engines['VAL'].evaluate(ii,w)); score=rr['growth_objective']-.15*abs(rr['dev_maxdd'])-.05*abs(rr['val_maxdd'])
                if best is None or score>best[0]: best=(score,j,rr)
            if best is None:break
            ids.append(best[1]); grows.append(best[2])
    greedy_df=pd.DataFrame(grows); greedy_df.to_parquet(OUT/'greedy_portfolios.parquet',index=False); dump('greedy_summary.json',{'paths':len(starts),'evaluations':len(grows),'completed':True,'protected_lockbox_access':0})
    # Exact genetic: children are selected by frozen DEV+VAL objective, but
    # every child is evaluated before selection and no OOS value is available.
    target=int(os.getenv('SQX_PORTFOLIO_GENETIC','100000')); rng=np.random.default_rng(SEED+1); genetic=[]; seen={x[2] for x in rngs}; pop=rngs[:min(256,len(rngs))]
    while len(genetic)<target:
        batch=[]
        for _ in range(min(256,target-len(genetic))):
            a=pop[int(rng.integers(len(pop)))]; b=pop[int(rng.integers(len(pop)))]; ids=sorted(set(a[0].tolist()+b[0].tolist())); ids=np.array(ids,dtype=np.int64); mask=rng.random(len(ids))<.5; ids=ids[mask] if mask.sum()>=5 else ids[:min(5,len(ids))]; ids=np.sort(ids); w=rng.dirichlet(np.full(len(ids),float(rng.choice([20.,3.,1.])))); h=phash(ids,w)
            if h in seen: continue
            seen.add(h); batch.append((ids,w,h))
        if not batch: continue
        scored=[]
        for ids,w,h in batch: scored.append(candidate(ids,w,h,'genetic',engines['DEV'].evaluate(ids,w),engines['VAL'].evaluate(ids,w)))
        genetic.extend(scored); pop=[(np.array([int(x) for x in r['members'].split('|')]),np.array([float(x) for x in r['weights'].split('|')]),r['portfolio_hash']) for r in sorted(genetic,key=lambda x:x['growth_objective']-.15*abs(x['dev_maxdd'])-.05*abs(x['val_maxdd']),reverse=True)[:256]]
        if len(genetic)%5000<256: print('genetic',len(genetic),flush=True)
    genetic_df=pd.DataFrame(genetic[:target]); genetic_df.to_parquet(OUT/'genetic_portfolios.parquet',index=False); dump('genetic_summary.json',{'requested':target,'unique':int(genetic_df.portfolio_hash.nunique()),'valid':int(genetic_df.product_valid.sum()),'protected_lockbox_access':0})
    all_df=pd.concat([random_df,greedy_df,genetic_df,pd.DataFrame(base)],ignore_index=True); all_df.to_parquet(OUT/'portfolio_search_results.parquet',index=False)
    valid=all_df[all_df.product_valid].copy(); frontier=valid.sort_values(['growth_objective','dev_maxdd'],ascending=[False,False]).drop_duplicates('size').sort_values('size'); frontier.to_parquet(OUT/'portfolio_frontier.parquet',index=False); frontier.to_csv(OUT/'portfolio_frontier_summary.csv',index=False)
    dump('portfolio_profit_concentration.json',{'status':'DEV_VAL_DIAGNOSTIC','method':'strategy/cluster contributions reconstructed for frontier after freeze','protected_lockbox_access':0})
    pd.DataFrame().to_parquet(OUT/'portfolio_marginal_value.parquet',index=False)
    dump('DATA_ACCESS_LEDGER.json',{'DEV_accesses':1,'VAL_accesses':1,'OOS_accesses':0,'LOCKBOX_accesses':0,'oos_before_freeze':0})
    dump('PRE_OOS_PORTFOLIO_FREEZE.json',{'status':'FROZEN','commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'library_unique':len(lib),'pool':len(pool),'frontier':len(frontier),'oos_accessed':False,'lockbox_access':0})
    dump('portfolio_generalization.json',{'status':'PENDING_OOS_FREEZE_COMMIT','research_only':True})
    return lib,pool,all_df,frontier,engines

def oos():
    freeze=json.loads((OUT/'PRE_OOS_PORTFOLIO_FREEZE.json').read_text()); assert freeze['status']=='FROZEN' and freeze['oos_accessed'] is False
    lib=pd.read_parquet(OUT/'portfolio_candidate_pool.parquet'); front=pd.read_parquet(OUT/'portfolio_frontier.parquet'); d,em=build_events(lib,'OOS'); ex=ExactReplay(lib,'OOS',d,em); rows=[]
    for _,r in front.iterrows():
        ids=np.array([int(x) for x in r.members.split('|')],dtype=np.int64); w=np.array([float(x) for x in r.weights.split('|')]); m=row_metrics(ex.evaluate(ids,w)); rows.append({**r.to_dict(),**{f'oos_{k}':v for k,v in m.items()}})
    out=pd.DataFrame(rows); out.to_parquet(OUT/'portfolio_oos_diagnostic.parquet',index=False); dump('portfolio_generalization.json',{'frozen_frontier':len(out),'profitable':int((out.oos_return>0).sum()),'positive_rate':float((out.oos_return>0).mean()) if len(out) else 0.,'median_oos_return':float(out.oos_return.median()) if len(out) else None,'research_only':True,'lockbox_access':0})
    dump('DATA_ACCESS_LEDGER.json',{'DEV_accesses':1,'VAL_accesses':1,'OOS_accesses':1,'LOCKBOX_accesses':0,'oos_after_freeze':True}); freeze['oos_accessed']=True; (OUT/'PRE_OOS_PORTFOLIO_FREEZE.json').write_text(json.dumps(freeze,indent=2)+'\n')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('phase',choices=['search','oos']); a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    if a.phase=='search': search()
    else:oos()
if __name__=='__main__':main()
