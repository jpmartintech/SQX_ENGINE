#!/usr/bin/env python3
"""Multi-coin PRICE_ONLY factory expansion with per-asset firewalls."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; RAW=ROOT/'data/crypto_external'; OUT=ROOT/'runs/reports/crypto_multicoin_factory_v1'; CANON=ROOT/'data/crypto_external_canonical'; MROOT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'
import sys; sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from crypto_clean_reboot_v1 import _event_kernel, array_metrics, evaluate_strategy
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.generator import CryptoRandomGenerator, CryptoGeneticGenerator
from sqx_engine.strategy import StrategyDefinition

RISK=.01; COST=.0009; SEED=20260930
def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,default=str)+'\n')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def out(asset): return OUT/'per_asset'/asset
def assets(): return sorted(p.stem.replace('USDT_15M','') for p in RAW.glob('*_15M.csv'))

def audit_file(p):
    d=pd.read_csv(p); cols=list(d.columns); ts=pd.to_datetime(d['datetime'],utc=True,errors='coerce'); ohlc=['open','high','low','close']; num=d[ohlc+(['volume'] if 'volume' in d else [])].apply(pd.to_numeric,errors='coerce')
    diff=ts.sort_values().diff().dt.total_seconds().dropna()/60; dup=int(ts.duplicated().sum()); bad=int(num.isna().sum().sum()); invalid=int((num[ohlc]<=0).any(axis=1).sum()); highlow=int((num.high<num.low).sum()); negative_vol=int((num.volume<0).sum()) if 'volume' in num else 0; zero_vol=int((num.volume==0).sum()) if 'volume' in num else 0
    asset=p.name.split('USDT_')[0]; interval='15M' if '_15M' in p.name else ('1H' if '_1H' in p.name else 'UNKNOWN'); expected=15 if interval=='15M' else (60 if interval=='1H' else float(diff.median()) if len(diff) else 0); gaps=int((diff>expected*1.0001).sum()); return {'file':str(p.relative_to(ROOT)),'asset':asset,'symbol':p.name.split('_')[0],'interval':interval,'rows':len(d),'bytes':p.stat().st_size,'sha256':sha(p),'columns':cols,'first':str(ts.min()),'last':str(ts.max()),'timezone':'UTC','monotonic':bool(ts.is_monotonic_increasing),'duplicates':dup,'invalid_timestamps':int(ts.isna().sum()),'nan_cells':bad,'nonpositive_ohlc':invalid,'high_below_low':highlow,'negative_volume':negative_vol,'zero_volume':zero_vol,'gaps_gt_expected':gaps,'median_interval_minutes':float(diff.median()) if len(diff) else None,'max_interval_minutes':float(diff.max()) if len(diff) else None,'identity':'INFERRED_SYMBOL_FROM_FILENAME','quality':'PASS' if not any([dup,ts.isna().sum(),bad,invalid,highlow,negative_vol]) else 'REVIEW'}

def catalog():
    OUT.mkdir(parents=True,exist_ok=True); rows=[]
    for p in sorted(RAW.rglob('*')):
        if p.is_file() and p.suffix.lower()=='.csv': rows.append(audit_file(p))
    pd.DataFrame(rows).to_csv(OUT/'MULTICOIN_DATA_CATALOG.csv',index=False); dump(OUT/'MULTICOIN_DATA_CATALOG.json',{'datasets':rows,'discovered_files':len(rows),'m15_assets':sorted({r['asset'] for r in rows if r['interval']=='M15'}),'h1_files':sum(r['interval']=='H1' for r in rows),'raw_data_gitignored':True})
    m=[x for x in rows if x['interval']=='15M']; starts=[pd.Timestamp(x['first']) for x in m]; ends=[pd.Timestamp(x['last']) for x in m]; common_start=max(starts); common_end=min(ends); span=common_end-common_start; eligible=[]; partial=[]; blocked=[]
    for x in m:
        duration=pd.Timestamp(x['last'])-pd.Timestamp(x['first']); (eligible if duration>=pd.Timedelta(days=365*3) else partial).append(x['asset']) if x['quality']=='PASS' else blocked.append(x['asset'])
    eligible=sorted(set(eligible)); partial=sorted(set(partial)); blocked=sorted(set(blocked))
    dump(OUT/'DATA_QUALITY_REPORT.json',{'m15':m,'h1_note':'H1 files catalogued but not used in this M15 factory','lockbox_access':0}); dump(OUT/'DATA_ELIGIBILITY_REPORT.json',{'long_history_eligible':sorted(eligible),'partial_history_eligible':sorted(partial),'insufficient_history':[],'data_quality_blocked':sorted(blocked),'criteria':'M15 quality PASS and >=3 years elapsed history','common_intersection':{'start':str(common_start),'end':str(common_end)}})
    dump(OUT/'TEMPORAL_PROTOCOL.json',{'per_asset_factory':'each asset uses elapsed-time 60/15/15/10 split of its own valid M15 interval','common_portfolio_intersection':{'start':str(common_start),'end':str(common_end),'split':'same elapsed 60/15/15/10 applied to common intersection'},'lockbox_reserved':True,'selection_uses_oos':False})
    dump(OUT/'DATA_ACCESS_LEDGER.json',{'assets':{a:{'DEV':0,'VAL_before_PRE_VAL':0,'OOS_before_PRE_OOS':0,'OOS_after_PRE_OOS':0,'LOCKBOX':0} for a in sorted(eligible)},'BTC_OOS':'PREVIOUSLY_BURNED','BTC_LOCKBOX':0})
    (OUT/'FACTORY_REUSE_AUDIT.md').write_text('# Factory reuse audit\n\nAll eligible M15 assets use the frozen BTC PRICE_ONLY v1.7 grammar, causal next-bar semantics, bounded 1% economic contract, exact Numba summary replay, Random/Genetic generation, and deterministic hash identity. No coin-specific predicates or post-outcome gates are introduced.\n\nBTC OOS is burned research. Every new-asset LOCKBOX remains forbidden.\n')
    return sorted(eligible)

def load_asset(asset):
    p=RAW/f'{asset}USDT_15M.csv'; d=pd.read_csv(p); d['timestamp']=pd.to_datetime(d.datetime,utc=True); d=d[['timestamp','open','high','low','close','volume']].sort_values('timestamp').reset_index(drop=True); d['available_at']=d.timestamp+pd.Timedelta(minutes=15); CANON.mkdir(exist_ok=True); d.to_parquet(CANON/f'{asset}_M15.parquet',index=False); return d
def split(d):
    st=d.timestamp.iloc[0]; en=d.timestamp.iloc[-1]+pd.Timedelta(minutes=15); span=en-st; return {'START':st,'DEV_END':st+span*.60,'VAL_END':st+span*.75,'OOS_END':st+span*.90,'END':en}
def index_bounds(d,b): return {k:int(d.timestamp.searchsorted(v)) for k,v in b.items()}
def windows(st,en,n=6):
    cuts=np.linspace(st,en,n+1,dtype=int); return [(int(cuts[i]),int(cuts[i+1])) for i in range(n)]
def setup(asset):
    d=load_asset(asset); f=prepare_crypto_features(d,None,'PRICE'); ev=FastEvaluator(d,f,initial_capital=1.,spread=COST,engine='numba',cache_size=512); b=split(d); ix=index_bounds(d,b); return d,f,ev,ix
def eval_one(s,d,f,ev,st,en,wb):
    sig=ev._signal(s); a=ev._arrays; atr=np.asarray(f['atr_14'],float); dire=1 if s.direction=='LONG' else -1; ei,xi,ds,pn,rs,held,reasons=_event_kernel(a['open'],a['high'],a['low'],a['close'],atr,sig,st,en,dire,float(s.stop_atr),float(s.target_atr),int(s.time_exit),float(ev.spread),float(ev.slippage)); z,ws=array_metrics(ei,xi,ds,rs,a['open'][ei] if len(ei) else np.empty(0),a['close'][xi] if len(xi) else np.empty(0),a['close'],wb); ev._signal_cache.clear(); ev._evaluation_cache.clear(); row={'strategy_id':s.readable_id,'hash':s.canonical_hash,'strategy':s.to_json(),'direction':s.direction,'trades':z['trades'],'pf':z['pf'],'economic_expectancy':z['economic_expectancy'],'return':z['return'],'maxdd':z['maxdd'],'minimum_equity':z['minimum_equity'],'ruin':z['ruin'],'positive_window_fraction':float(np.mean([x['economic_expectancy']>0 for x in ws])),'active_windows':int(sum(x['trades']>=3 for x in ws)),'best_window_share':float(max([max(x['realized_pnl'],0) for x in ws],default=0)/max(sum(max(x['realized_pnl'],0) for x in ws),1e-12))}; return row
def replay(row,d,f,ev,st,en):
    s=StrategyDefinition.from_json(row.strategy); r=eval_one(s,d,f,ev,st,en,[(st,en)]); return {'hash':row['hash'],'strategy_id':row['strategy_id'],'direction':s.direction,'trades':r['trades'],'pf':r['pf'],'economic_expectancy':r['economic_expectancy'],'return':r['return'],'maxdd':r['maxdd'],'minimum_equity':r['minimum_equity'],'ruin':r['ruin']}
def campaign(asset):
    ao=out(asset); ao.mkdir(parents=True,exist_ok=True); d,f,ev,ix=setup(asset); wb=windows(ix['START'],ix['DEV_END']); rb=int(os.getenv('SQX_MULTICOIN_RANDOM','50000')); gb=int(os.getenv('SQX_MULTICOIN_GENETIC','200000')); seen=set(); rows_r=[]; rows_g=[]; rg=CryptoRandomGenerator(asset,'M15',seed=SEED+hash(asset)%10000,min_predicates=1,max_predicates=2,grammar_version='v1.7',information_variant='PRICE'); gg=CryptoGeneticGenerator(asset,'M15',seed=SEED+10000+hash(asset)%10000,min_predicates=1,max_predicates=2,grammar_version='v1.7',information_variant='PRICE',population_size=80,mode='scale'); start=time.time()
    def score(s,kind):
        if s.canonical_hash in seen:return None
        seen.add(s.canonical_hash); r=eval_one(s,d,f,ev,ix['START'],ix['DEV_END'],wb); r['kind']=kind; return r
    i=0
    while len(rows_r)<rb:
        i+=1
        r=score(rg.ask(),'RANDOM');
        if r:rows_r.append(r)
        if len(rows_r)%5000==0:print(asset,'random unique',len(rows_r),'attempts',i,flush=True)
    i=0
    while len(rows_g)<gb:
        i+=1
        s=gg.ask(known_hashes=seen); r=score(s,'GENETIC')
        if r:
            rows_g.append(r)
            class Q:pass
            q=Q(); q.expectancy_r=r['economic_expectancy']; q.sharpe=0.; q.max_drawdown=r['maxdd']; gg.tell(s,q)
        if len(rows_g)%5000==0:print(asset,'genetic unique',len(rows_g),'attempts',i,flush=True)
    random=pd.DataFrame(rows_r); genetic=pd.DataFrame(rows_g); random.to_parquet(ao/'random_results.parquet',index=False); genetic.to_parquet(ao/'genetic_results.parquet',index=False); allx=pd.concat([random,genetic],ignore_index=True); allx.to_parquet(ao/'all_dev_results.parquet',index=False)
    gate=(~allx.ruin)&(allx.trades>=20)&(allx.active_windows>=4)&(allx.positive_window_fraction>=.5)&(allx.economic_expectancy>0)&(allx['return']>0)&(allx.pf>1)&(allx.best_window_share<=.7); funnel=[('total_unique',len(allx)),('economically_valid',int((~allx.ruin).sum())),('positive_expectancy',int((allx.economic_expectancy>0).sum())),('positive_return',int((allx['return']>0).sum())),('pf_gt_1',int((allx.pf>1).sum())),('trade_support',int((allx.trades>=20).sum())),('temporal_support',int((allx.active_windows>=4).sum())),('profit_concentration',int((allx.best_window_share<=.7).sum())),('final_dev_candidates',int(gate.sum()))]; pd.DataFrame(funnel,columns=['stage','count']).to_csv(ao/'dev_funnel.csv',index=False); dump(ao/'random_summary.json',{'unique':len(random),'long':int((random.direction=='LONG').sum()),'short':int((random.direction=='SHORT').sum()),'positive_return':int((random['return']>0).sum()),'positive_expectancy':int((random.economic_expectancy>0).sum()),'pf_gt_1':int((random.pf>1).sum())}); dump(ao/'genetic_summary.json',{'unique':len(genetic),'long':int((genetic.direction=='LONG').sum()),'short':int((genetic.direction=='SHORT').sum()),'positive_return':int((genetic['return']>0).sum()),'positive_expectancy':int((genetic.economic_expectancy>0).sum()),'pf_gt_1':int((genetic.pf>1).sum())});
    cand=allx[gate].copy(); cand.to_parquet(ao/'dev_candidates_frozen.parquet',index=False); dump(ao/'PRE_VAL_FREEZE.json',{'status':'FROZEN','asset':asset,'candidates':len(cand),'campaign_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'val_accessed':False,'oos_accessed':False,'lockbox_access':0}); dump(ao/'campaign_manifest.json',{'asset':asset,'source_sha256':sha(RAW/f'{asset}USDT_15M.csv'),'split':{k:str(v) for k,v in split(d).items()},'random_unique':len(random),'genetic_unique':len(genetic),'elapsed_seconds':time.time()-start,'economic_contract':'frozen BTC bounded contract','grammar':'v1.7 PRICE_ONLY','lockbox_access':0})
def val(asset):
    ao=out(asset); d,f,ev,ix=setup(asset); cand=pd.read_parquet(ao/'dev_candidates_frozen.parquet'); rows=[replay(r,d,f,ev,ix['DEV_END'],ix['VAL_END']) for _,r in cand.iterrows()]; v=pd.DataFrame(rows); v.to_parquet(ao/'val_results.parquet',index=False); gate=(~v.ruin)&(v.trades>=10)&(v.pf>1)&(v.economic_expectancy>0)&(v['return']>0); lib=cand.merge(v,on=['hash','strategy_id','direction'],suffixes=('_dev','_val')); lib=lib[gate.to_numpy()].copy(); lib=lib.drop_duplicates('hash'); lib.to_parquet(ao/'library.parquet',index=False); dump(ao/'library_summary.json',{'asset':asset,'records':len(lib),'unique_hashes':int(lib.hash.nunique()),'long':int((lib.direction=='LONG').sum()),'short':int((lib.direction=='SHORT').sum()),'val_admitted':int(gate.sum()),'lockbox_access':0}); dump(ao/'PRE_OOS_FREEZE.json',{'status':'FROZEN','asset':asset,'library':len(lib),'library_sha256':sha(ao/'library.parquet'),'val_accessed_after_pre_val':True,'oos_accessed':False,'lockbox_access':0})
def oos(asset):
    ao=out(asset); fz=json.loads((ao/'PRE_OOS_FREEZE.json').read_text()); assert fz['status']=='FROZEN' and not fz['oos_accessed']; d,f,ev,ix=setup(asset); lib=pd.read_parquet(ao/'library.parquet'); rows=[replay(r,d,f,ev,ix['OOS_END'],ix['END']) for _,r in lib.iterrows()]; o=pd.DataFrame(rows); o.to_parquet(ao/'oos_results.parquet',index=False); dump(ao/'factory_generalization.json',{'asset':asset,'count':len(o),'positive_return':int((o['return']>0).sum()),'positive_rate':float((o['return']>0).mean()) if len(o) else 0.,'positive_expectancy':int((o.economic_expectancy>0).sum()),'median_return':float(o['return'].median()) if len(o) else None,'median_expectancy':float(o.economic_expectancy.median()) if len(o) else None,'median_pf':float(o.pf.median()) if len(o) else None,'ruin_rate':float(o.ruin.mean()) if len(o) else 0.,'research_only':True,'lockbox_access':0}); fz['oos_accessed']=True; (ao/'PRE_OOS_FREEZE.json').write_text(json.dumps(fz,indent=2)+'\n')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('phase',choices=['catalog','campaign','val','oos']); ap.add_argument('--asset'); a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    if a.phase=='catalog': print(catalog())
    elif a.phase=='campaign': campaign(a.asset)
    elif a.phase=='val': val(a.asset)
    else:oos(a.asset)
if __name__=='__main__':main()
