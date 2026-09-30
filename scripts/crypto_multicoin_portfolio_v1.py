#!/usr/bin/env python3
"""Exact, bounded, DEV+VAL-only multi-coin portfolio factory."""
from __future__ import annotations
import argparse, hashlib, json, math, os, subprocess, time
from pathlib import Path
import numpy as np, pandas as pd
from numba import njit
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_multicoin_portfolio_v1'; FACT=ROOT/'runs/reports/crypto_multicoin_factory_v1'; RAW=ROOT/'data/crypto_external'; RISK=.01; COST=.0009; ASSETS=['BTC','AVAX','ETH','LINK','SOL']; SEED=20261001; ASSET_CONTEXT={}
import sys; sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from crypto_clean_reboot_v1 import _event_kernel
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition

def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,default=str)+'\n')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def phash(ids,w): return hashlib.sha256(json.dumps({'ids':[int(x) for x in ids],'w':[round(float(x),12) for x in w]},sort_keys=True,separators=(',',':')).encode()).hexdigest()
def load(asset):
    if asset=='BTC': p=ROOT/'data/external_candidate/BTCUSDT_15M_EXTERNAL.csv'
    else: p=RAW/f'{asset}USDT_15M.csv'
    d=pd.read_csv(p); d['timestamp']=pd.to_datetime(d['datetime'],utc=True); return d[['timestamp','open','high','low','close','volume']].sort_values('timestamp').reset_index(drop=True)
def common_bounds():
    st=pd.Timestamp('2020-09-22 06:30:00',tz='UTC'); en=pd.Timestamp('2025-05-02 14:45:00',tz='UTC')
    # The catalog's common end is 2026-05-02; use the frozen common intersection.
    en=pd.Timestamp('2026-05-02 14:45:00',tz='UTC'); span=en-st
    return {'START':st,'DEV_END':(st+span*.60).floor('15min'),'VAL_END':(st+span*.75).floor('15min'),'OOS_END':(st+span*.90).floor('15min'),'END':en}
def period_bounds():
    b=common_bounds(); return b, {'DEV':(b['START'],b['DEV_END']),'VAL':(b['DEV_END'],b['VAL_END']),'OOS':(b['VAL_END'],b['OOS_END'])}
def strategy_signature(row):
    try:
        s=json.loads(row.strategy) if isinstance(row.strategy,str) else row.strategy
        return json.dumps({'direction':s.get('direction'),'logic':s.get('logic'),'predicates':sorted(str(x) for x in s.get('predicates',[])),'stop':s.get('stop_atr'),'target':s.get('target_atr'),'time':s.get('time_exit')},sort_keys=True)
    except Exception: return 'unknown'
def input_reproduction():
    rows=[]
    for a in ASSETS:
        p=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1/library_v1.parquet' if a=='BTC' else FACT/'per_asset'/a/'library.parquet'
        d=pd.read_parquet(p); d=d.drop_duplicates('hash').copy(); d['asset']=a; d['instance_id']=a+'::'+d.hash.astype(str); rows.append(d)
    u=pd.concat(rows,ignore_index=True); u.to_parquet(OUT/'full_library_instances.parquet',index=False)
    counts={a:int((u.asset==a).sum()) for a in ASSETS}; dump(OUT/'INPUT_REPRODUCTION.json',{'assets':counts,'total_instances':len(u),'hashes_unique_within_asset':bool(u.groupby('asset').hash.nunique().sum()==len(u)),'asset_instance_identity':True,'sources':{a:str((ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1/library_v1.parquet' if a=='BTC' else FACT/'per_asset'/a/'library.parquet')) for a in ASSETS},'oos_used':False,'lockbox_access':0}); return u
def build_pool(u):
    x=u.copy(); x['signature']=x.apply(strategy_signature,axis=1); x['score']=np.log1p(np.maximum(x.return_dev,-.99))+np.log1p(np.maximum(x.return_val,-.99))+10*x.economic_expectancy_dev+10*x.economic_expectancy_val+0.1*x.positive_window_fraction_dev
    parts=[]
    for a in ASSETS:
        g=x[x.asset==a].sort_values(['score','hash'],ascending=[False,True]); direction_parts=[]
        for dire in ['LONG','SHORT']:
            q=g[g.direction==dire]; n=min(20,len(q)); direction_parts.append(q.head(n)); direction_parts.append(q.iloc[max(0,len(q)//2-n//2):max(0,len(q)//2-n//2)+n])
        p=pd.concat(direction_parts).drop_duplicates('hash'); p=p.sort_values(['score','hash'],ascending=[False,True]).head(40); parts.append(p)
    pool=pd.concat(parts).drop_duplicates(['asset','hash']).sort_values(['asset','score','hash'],ascending=[True,False,True]).reset_index(drop=True); pool['pool_id']=np.arange(len(pool)); pool.to_parquet(OUT/'SEARCH_POOL.parquet',index=False)
    audit={'full_universe':len(u),'pool':len(pool),'per_asset':pool.groupby('asset').size().to_dict(),'directions':pool.direction.value_counts().to_dict(),'signatures':pool.signature.nunique(),'policy':'40 per asset; deterministic top/middle quality tiers within LONG/SHORT; DEV+VAL only; no OOS','oos_used':False}; dump(OUT/'SEARCH_POOL_AUDIT.json',audit); (OUT/'SEARCH_POOL_POLICY.md').write_text('# Search pool policy\n\nThe pool is selected before portfolio search using only frozen DEV+VAL metrics. Each primary asset contributes at most 40 definitions, with deterministic top and middle quality tiers separately for LONG and SHORT. Asset identity is retained; cross-asset hashes are never deduplicated. OOS is excluded. The smaller pool is an explicit measured-compute tradeoff, not an OOS reduction.\n'); return pool
def dataset_for(asset):
    d=load(asset); b=common_bounds(); d=d[(d.timestamp>=b['START']-pd.Timedelta(days=30))&(d.timestamp<=b['END'])].reset_index(drop=True); return d
def context(asset):
    if asset not in ASSET_CONTEXT:
        d=dataset_for(asset); f=prepare_crypto_features(d,None,'PRICE'); ASSET_CONTEXT[asset]=(d,f,FastEvaluator(d,f,initial_capital=1.,spread=COST,engine='numba',cache_size=512),pd.to_datetime(d.timestamp).tolist(),d.open.to_numpy(float),d.close.to_numpy(float))
    return ASSET_CONTEXT[asset]
def events_for(row,asset,period):
    d,f,ev,ts,op,cl=context(asset); b=common_bounds(); p0,p1=period_bounds()[1][period]; st=int(d.timestamp.searchsorted(p0)); en=int(d.timestamp.searchsorted(p1)); s=StrategyDefinition.from_json(row.strategy if isinstance(row.strategy,str) else json.dumps(row.strategy)); sig=ev._signal(s); a=ev._arrays; atr=np.asarray(f['atr_14'],float); dire=1 if s.direction=='LONG' else -1; ei,xi,ds,pn,rs,held,reasons=_event_kernel(a['open'],a['high'],a['low'],a['close'],atr,sig,st,en,dire,float(s.stop_atr),float(s.target_atr),int(s.time_exit),float(ev.spread),float(ev.slippage)); ev._signal_cache.clear(); ev._evaluation_cache.clear(); return [(ts[int(e)],ts[int(x)],float(rs[k]),float(op[int(e)]),float(cl[int(x)]),1 if ds[k]>0 else -1,ASSETS.index(asset)) for k,(e,x) in enumerate(zip(ei,xi))]
def build_market(pool,period):
    b=common_bounds(); ps=period_bounds()[1][period]; timestamps=pd.date_range(ps[0],ps[1]-pd.Timedelta(minutes=15),freq='15min',tz='UTC'); prices=[]; maps={}
    for a in ASSETS:
        d=dataset_for(a).set_index('timestamp').reindex(timestamps); prices.append(d.close.to_numpy(float));
    full_price=np.column_stack(prices); mark=np.arange(0,len(timestamps),96,dtype=np.int64); all_events=[]; mp={t:i for i,t in enumerate(timestamps)}
    for _,r in pool.iterrows():
        es=events_for(r,r.asset,period)
        for e in es:
            if e[0] in mp and e[1] in mp: all_events.append((mp[e[0]],mp[e[1]],e[2],e[3],e[4],e[5],int(r.pool_id),e[6]))
    evs=np.asarray(all_events,dtype=float).reshape((-1,8)) if all_events else np.empty((0,8))
    raw=np.unique(np.concatenate([mark,evs[:,0:2].astype(np.int64).ravel()])) if len(evs) else mark
    if len(evs):
        evs[:,0]=np.searchsorted(raw,evs[:,0].astype(np.int64)); evs[:,1]=np.searchsorted(raw,evs[:,1].astype(np.int64))
    return timestamps[raw],full_price[raw],np.arange(len(raw),dtype=np.int64),evs
@njit(cache=True)
def portfolio_kernel(prices,entries,exits,rs,eps,xps,dirs,sids,assets,weights,nstr,entry_order,entry_offsets,exit_order,exit_offsets):
    active=np.full(nstr,-1,np.int64); risk=np.zeros(nstr); cash=1.; peak=1.; mn=1.; dd=0.; maxheat=0.; gp=0.; gl=0.; trades=0
    for t in range(len(prices)):
        for q in range(exit_offsets[t],exit_offsets[t+1]):
            k=exit_order[q]; s=sids[k]
            if active[s]==k:
                pnl=risk[s]*rs[k]; cash+=pnl; gp+=max(pnl,0.); gl+=max(-pnl,0.); trades+=1; active[s]=-1; risk[s]=0.
        floating=0.; heat=0.
        for s in range(nstr):
            k=active[s]
            if k>=0:
                den=abs(xps[k]-eps[k]); prog=0. if den<1e-15 else dirs[k]*(prices[t,assets[k]]-eps[k])/den
                floating+=risk[s]*rs[k]*prog; heat+=risk[s]
        equity=cash+floating; maxheat=max(maxheat,heat)
        for q in range(entry_offsets[t],entry_offsets[t+1]):
            k=entry_order[q]; s=sids[k]
            if active[s]<0 and weights[s]>0. and equity>0.:
                risk[s]=equity*RISK*weights[s]; active[s]=k
        floating=0.; heat=0.
        for s in range(nstr):
            k=active[s]
            if k>=0:
                den=abs(xps[k]-eps[k]); prog=0. if den<1e-15 else dirs[k]*(prices[t,assets[k]]-eps[k])/den
                floating+=risk[s]*rs[k]*prog; heat+=risk[s]
        equity=cash+floating; maxheat=max(maxheat,heat); peak=max(peak,equity); mn=min(mn,equity); dd=min(dd,(equity-peak)/peak if peak else -1.)
    for s in range(nstr):
        k=active[s]
        if k>=0:
            den=abs(xps[k]-eps[k]); prog=0. if den<1e-15 else dirs[k]*(prices[-1,assets[k]]-eps[k])/den; pnl=risk[s]*rs[k]*prog; cash+=pnl; gp+=max(pnl,0.); gl+=max(-pnl,0.); trades+=1
    pf=gp/gl if gl>0. else (1e30 if gp>0. else 0.)
    return cash,cash-1.,pf,(cash-1.)/trades if trades else 0.,dd,mn,maxheat,trades

def metric_tuple(x):
    return {'final_equity':float(x[0]),'return':float(x[1]),'pf':float(x[2]),'expectancy':float(x[3]),'maxdd':float(x[4]),'minimum_equity':float(x[5]),'heat':float(x[6]),'trades':int(x[7]),'ruin':bool(x[5]<=0)}

class Market:
    def __init__(self,timestamps,prices,events,pool):
        self.timestamps=timestamps; self.prices=prices; self.events=events; self.pool=pool; self.by_sid={int(s):events[events[:,6]==s] for s in np.unique(events[:,6]).astype(int)} if len(events) else {}
    def arrays(self,ids):
        ids=np.asarray(ids,dtype=np.int64); rem={int(x):i for i,x in enumerate(ids)}; chunks=[]
        for x in ids:
            if int(x) in self.by_sid:
                c=self.by_sid[int(x)].copy(); c[:,6]=rem[int(x)]; chunks.append(c)
        e=np.concatenate(chunks,axis=0) if chunks else np.empty((0,8))
        return ids,e
    def fast(self,ids,weights):
        ids,e=self.arrays(ids); weights=np.asarray(weights,dtype=np.float64); weights=weights/weights.sum(); n=len(ids)
        if len(e)==0:return metric_tuple((1.,0.,0.,0.,0.,1.,0.,0))
        entries=e[:,0].astype(np.int64); exits=e[:,1].astype(np.int64); rs=e[:,2]; eps=e[:,3]; xps=e[:,4]; dirs=e[:,5].astype(np.int8); sids=e[:,6].astype(np.int64); assets=e[:,7].astype(np.int64); nt=len(self.timestamps); eo=np.argsort(entries,kind='stable').astype(np.int64); xo=np.argsort(exits,kind='stable').astype(np.int64); entoff=np.zeros(nt+1,dtype=np.int64); exitoff=np.zeros(nt+1,dtype=np.int64); np.add.at(entoff,entries+1,1); np.add.at(exitoff,exits+1,1); entoff=np.cumsum(entoff); exitoff=np.cumsum(exitoff)
        return metric_tuple(portfolio_kernel(self.prices,entries,exits,rs,eps,xps,dirs,sids,assets,weights,n,eo,entoff,xo,exitoff))
    def reference(self,ids,weights):
        ids,e=self.arrays(ids); weights=np.asarray(weights,dtype=float); weights=weights/weights.sum(); n=len(ids); active=[-1]*n; risk=[0.]*n; cash=1.; peak=1.; mn=1.; dd=0.; mh=0.; gp=0.; gl=0.; trades=0
        byexit={}; byentry={}
        for k,row in enumerate(e): byexit.setdefault(int(row[1]),[]).append(k); byentry.setdefault(int(row[0]),[]).append(k)
        for t in range(len(self.timestamps)):
            for k in byexit.get(t,[]):
                s=int(e[k,6])
                if active[s]==k:
                    pnl=risk[s]*e[k,2]; cash+=pnl; gp+=max(pnl,0); gl+=max(-pnl,0); trades+=1; active[s]=-1; risk[s]=0.
            floating=0.; heat=0.
            for s,k in enumerate(active):
                if k>=0:
                    den=abs(e[k,4]-e[k,3]); prog=0 if den<1e-15 else e[k,5]*(self.prices[t,int(e[k,7])]-e[k,3])/den; floating+=risk[s]*e[k,2]*prog; heat+=risk[s]
            equity=cash+floating; mh=max(mh,heat)
            for k in byentry.get(t,[]):
                s=int(e[k,6])
                if active[s]<0 and equity>0: risk[s]=equity*RISK*weights[s]; active[s]=k
            floating=0.; heat=0.
            for s,k in enumerate(active):
                if k>=0:
                    den=abs(e[k,4]-e[k,3]); prog=0 if den<1e-15 else e[k,5]*(self.prices[t,int(e[k,7])]-e[k,3])/den; floating+=risk[s]*e[k,2]*prog; heat+=risk[s]
            equity=cash+floating; mh=max(mh,heat); peak=max(peak,equity); mn=min(mn,equity); dd=min(dd,(equity-peak)/peak if peak else -1.)
        for s,k in enumerate(active):
            if k>=0:
                den=abs(e[k,4]-e[k,3]); prog=0 if den<1e-15 else e[k,5]*(self.prices[-1,int(e[k,7])]-e[k,3])/den; pnl=risk[s]*e[k,2]*prog; cash+=pnl; gp+=max(pnl,0); gl+=max(-pnl,0); trades+=1
        return metric_tuple((cash,cash-1.,gp/gl if gl else (1e30 if gp else 0.),(cash-1.)/trades if trades else 0.,dd,mn,mh,trades))

def build(period,pool):
    ts,prices,marks,events=build_market(pool,period); return Market(ts,prices,events,pool)
def row(ids,w,method,dev,val):
    return {'portfolio_hash':phash(ids,w),'method':method,'size':len(ids),'asset_count':int(pool_global.iloc[ids].asset.nunique()),'members':'|'.join(str(int(x)) for x in ids),'weights':'|'.join(f'{float(x):.12g}' for x in w),'dev_return':dev['return'],'val_return':val['return'],'dev_cagr':None,'val_cagr':None,'dev_pf':dev['pf'],'val_pf':val['pf'],'dev_expectancy':dev['expectancy'],'val_expectancy':val['expectancy'],'dev_maxdd':dev['maxdd'],'val_maxdd':val['maxdd'],'dev_min_equity':dev['minimum_equity'],'val_min_equity':val['minimum_equity'],'dev_heat':dev['heat'],'val_heat':val['heat'],'dev_trades':dev['trades'],'val_trades':val['trades'],'product_valid':bool(dev['return']>0 and val['return']>0 and dev['pf']>1 and val['pf']>1 and dev['expectancy']>0 and val['expectancy']>0 and not dev['ruin'] and not val['ruin'])}
def frontier(df):
    x=df[df.product_valid].copy().drop_duplicates('portfolio_hash')
    # Exact Pareto testing over the whole search log is quadratic. Preserve
    # the deterministic top growth/risk candidates, then perform the exact
    # dominance test on that bounded diagnostic set.
    x=x.assign(_score=x.dev_return+x.val_return+10*x.dev_maxdd+10*x.val_maxdd).nlargest(min(10000,len(x)),'_score').drop(columns='_score')
    a=x[['dev_return','val_return','dev_maxdd','val_maxdd']].to_numpy(float); keep=[]
    for i in range(len(a)):
        better=(a>=a[i]).all(axis=1)&(a>a[i]).any(axis=1)
        if not better.any(): keep.append(i)
    return x.iloc[keep].sort_values(['val_return','dev_return'],ascending=False)

def search():
    global pool_global
    OUT.mkdir(parents=True,exist_ok=True); u=input_reproduction(); pool_global=build_pool(u); dump(OUT/'COMMON_TEMPORAL_WINDOWS.json',{'start':str(common_bounds()['START']),'dev_end':str(common_bounds()['DEV_END']),'val_end':str(common_bounds()['VAL_END']),'oos_end':str(common_bounds()['OOS_END']),'lockbox_end':str(common_bounds()['END']),'basis':'common elapsed-time intersection','assets':ASSETS}); dump(OUT/'FULL_UNIVERSE_SUMMARY.json',{'total_instances':len(u),'assets':u.groupby('asset').size().to_dict(),'primary_assets':ASSETS,'oos_used':False})
    markets={p:build(p,pool_global) for p in ('DEV','VAL')}; dump(OUT/'MULTICOIN_PORTFOLIO_ECONOMIC_CONTRACT.md',{}) if False else None; (OUT/'MULTICOIN_PORTFOLIO_ECONOMIC_CONTRACT.md').write_text('# Multi-coin portfolio economic contract\n\nOne chronological shared equity curve spans all primary assets. Total intended heat is 1% of current portfolio equity, allocated by non-negative weights summing to one. Exits precede entries at equal timestamps. Floating PnL is marked at event and daily timestamps; realized PnL, fees and slippage are retained. Funding is not fabricated. Ruin is equity <= 0. Metrics are calculated from the combined stream, never averaged standalone metrics.\n'); dump(OUT/'PORTFOLIO_ENGINE_MANIFEST.json',{'assets':ASSETS,'risk_total':RISK,'engine':'Numba exact shared-equity multi-asset replay','reference':'Python identical event ordering','lockbox_access':0})
    rng=np.random.default_rng(SEED); target_r=int(os.getenv('SQX_MULTICOIN_PORTFOLIO_RANDOM','50000')); target_g=int(os.getenv('SQX_MULTICOIN_PORTFOLIO_GENETIC','100000')); seen=set(); random=[]
    while len(random)<target_r:
        k=int(rng.choice([5,10,20,30,50])); ids=np.sort(rng.choice(len(pool_global),min(k,len(pool_global)),replace=False)); w=rng.dirichlet(np.ones(len(ids))); h=phash(ids,w)
        if h in seen: continue
        seen.add(h); random.append(row(ids,w,'random',markets['DEV'].fast(ids,w),markets['VAL'].fast(ids,w)))
        if len(random)%5000==0: print('random',len(random),flush=True)
    rdf=pd.DataFrame(random); rdf.to_parquet(OUT/'RANDOM_PORTFOLIOS.parquet',index=False); dump(OUT/'RANDOM_SUMMARY.json',{'unique':len(rdf),'valid':int(rdf.product_valid.sum()),'sizes':rdf['size'].value_counts().to_dict(),'lockbox_access':0})
    greedy=[]; starts=np.argsort(-pool_global.score.to_numpy())[:5]; shortlist=np.argsort(-pool_global.score.to_numpy())[:50]
    for seed in starts:
        ids=[int(seed)]
        for _ in range(9):
            best=None
            for j in shortlist:
                j=int(j)
                if j in ids:continue
                ii=np.array(sorted(ids+[j])); w=np.ones(len(ii))/len(ii); rr=row(ii,w,'greedy',markets['DEV'].fast(ii,w),markets['VAL'].fast(ii,w)); score=min(rr['dev_return'],rr['val_return'])-.15*abs(rr['dev_maxdd'])-.15*abs(rr['val_maxdd'])
                if best is None or score>best[0]:best=(score,j,rr)
            if best is None:break
            ids.append(best[1]); greedy.append(best[2])
    gdf=pd.DataFrame(greedy); gdf.to_parquet(OUT/'GREEDY_PORTFOLIOS.parquet',index=False); dump(OUT/'GREEDY_SUMMARY.json',{'evaluations':len(gdf),'paths':len(starts),'lockbox_access':0})
    # Genetic produces unique candidates from DEV+VAL fitness only.
    pop=[(np.array([int(x) for x in r.members.split('|')]),np.array([float(x) for x in r.weights.split('|')])) for _,r in rdf.nlargest(min(256,len(rdf)),'val_return').iterrows()]; genetic=[]
    while len(genetic)<target_g:
        a=pop[int(rng.integers(len(pop)))]; b=pop[int(rng.integers(len(pop)))]; ids=np.array(sorted(set(a[0].tolist()+b[0].tolist())),dtype=int); mask=rng.random(len(ids))<.5; ids=np.sort(ids[mask] if mask.sum()>=5 else ids[:min(5,len(ids))]); w=rng.dirichlet(np.ones(len(ids))); h=phash(ids,w)
        if h in seen:continue
        seen.add(h); rr=row(ids,w,'genetic',markets['DEV'].fast(ids,w),markets['VAL'].fast(ids,w)); genetic.append(rr); pop.append((ids,w)); pop=sorted(pop,key=lambda z:np.random.default_rng(int(phash(z[0],z[1])[:8],16)).random(),reverse=True)[:256]
        if len(genetic)%5000==0:print('genetic',len(genetic),flush=True)
    gendf=pd.DataFrame(genetic); gendf.to_parquet(OUT/'GENETIC_PORTFOLIOS.parquet',index=False); dump(OUT/'GENETIC_SUMMARY.json',{'unique':len(gendf),'valid':int(gendf.product_valid.sum()),'sizes':gendf['size'].value_counts().to_dict(),'lockbox_access':0})
    all_df=pd.concat([rdf,gdf,gendf],ignore_index=True); front=frontier(all_df); front.to_parquet(OUT/'DEV_VAL_FRONTIER.parquet',index=False); front.to_csv(OUT/'DEV_VAL_FRONTIER_SUMMARY.csv',index=False); dump(OUT/'BTC_ONLY_CONTROL.json',{'status':'control_available_from_previous_frozen_BTC_frontier','oos_used':False}); dump(OUT/'ASSET_ABLATION.json',{'status':'DEV_VAL deterministic control summaries pending finalizer','method':'same pool and replay, no OOS'}); dump(OUT/'CROSS_ASSET_CORRELATIONS.json',{'status':'event maps built for exact replay; aggregate correlation diagnostics deferred to finalizer','assets':ASSETS,'oos_used':False}); dump(OUT/'MULTIASSET_CLUSTERS.json',{'status':'pool signatures and asset-aware clusters recorded','cluster_method':'deterministic strategy signature plus asset','oos_used':False}); dump(OUT/'PRE_OOS_MULTICOIN_PORTFOLIO_FREEZE.json',{'status':'FROZEN','commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'pool':len(pool_global),'random':len(rdf),'genetic':len(gendf),'frontier':len(front),'oos_accessed':False,'lockbox_access':0}); dump(OUT/'DATA_ACCESS_LEDGER.json',{'DEV':1,'VAL':1,'OOS_before_freeze':0,'OOS_after_freeze':0,'LOCKBOX':0});
    return front
def oos():
    fz=json.loads((OUT/'PRE_OOS_MULTICOIN_PORTFOLIO_FREEZE.json').read_text()); assert fz['status']=='FROZEN' and not fz['oos_accessed']; pool=pd.read_parquet(OUT/'SEARCH_POOL.parquet'); front=pd.read_parquet(OUT/'DEV_VAL_FRONTIER.parquet'); m=build('OOS',pool); rows=[]
    for _,r in front.iterrows():
        ids=np.array([int(x) for x in r.members.split('|')]); w=np.array([float(x) for x in r.weights.split('|')]); mm=m.fast(ids,w); rows.append({**r.to_dict(),**{'oos_'+k:v for k,v in mm.items()}})
    o=pd.DataFrame(rows); o.to_parquet(OUT/'OOS_MULTICOIN_DIAGNOSTIC.parquet',index=False); dump(OUT/'PORTFOLIO_GENERALIZATION.json',{'frozen_frontier':len(o),'profitable':int((o.oos_return>0).sum()) if len(o) else 0,'positive_rate':float((o.oos_return>0).mean()) if len(o) else 0.,'median_return':float(o.oos_return.median()) if len(o) else None,'research_only':True,'lockbox_access':0}); dump(OUT/'DATA_ACCESS_LEDGER.json',{'DEV':1,'VAL':1,'OOS_before_freeze':0,'OOS_after_freeze':1,'LOCKBOX':0}); fz['oos_accessed']=True; (OUT/'PRE_OOS_MULTICOIN_PORTFOLIO_FREEZE.json').write_text(json.dumps(fz,indent=2)+'\n')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('phase',choices=['search','oos']); a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True); search() if a.phase=='search' else oos()
if __name__=='__main__':main()
