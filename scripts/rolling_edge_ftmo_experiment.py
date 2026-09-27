"""Bounded rolling recent-edge -> exact FTMO Forward experiment."""
from __future__ import annotations
import argparse, hashlib, json, resource, time
from pathlib import Path
import numpy as np
import pandas as pd

from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.data.loader import load_ohlcv
from sqx_engine.features import prepare_features
from sqx_engine.generators import GeneticGenerator
from sqx_engine.portfolio_factory.ftmo_current import CurrentFtmoEvaluator, ftmo_2step_current_profile
from sqx_engine.rolling_edge import activity_metrics, rolling_cycles, strategy_gate

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/rolling_edge_ftmo_final"
DATA={('EURUSD','H1'):ROOT/'data/derived/EURUSD_H1_11d571e8bb3d_143197.csv',('EURUSD','M15'):ROOT/'data/cloud/EURUSD_M15.csv',('GBPUSD','H1'):ROOT/'data/derived/GBPUSD_H1_0fd4a5e80da9_143187.csv',('GBPUSD','M15'):ROOT/'data/cloud/GBPUSD_M15.csv',('NZDUSD','H1'):ROOT/'data/derived/NZDUSD_H1_0e91c0d12434_141524.csv',('NZDUSD','M15'):ROOT/'data/cloud/NZDUSD_M15.csv',('USDCAD','H1'):ROOT/'data/derived/USDCAD_H1_62a0d35bff6a_141588.csv',('USDCAD','M15'):ROOT/'data/cloud/USDCAD_M15.csv',('USDCHF','H1'):ROOT/'data/derived/USDCHF_H1_379cf0cf5c5a_143126.csv',('USDCHF','M15'):ROOT/'data/cloud/USDCHF_M15.csv',('USDJPY','H1'):ROOT/'data/derived/USDJPY_H1_4b4c1023d6ad_143174.csv',('USDJPY','M15'):ROOT/'data/cloud/USDJPY_M15.csv',('XAUUSD','H1'):ROOT/'data/derived/XAUUSD_H1_ace62dd3d22f_136885.csv',('XAUUSD','M15'):ROOT/'data/cloud/XAUUSD_M15.csv'}

def write(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+'\n')

def event_ledger(strategy,result,data,features,market,timeframe):
    ts={pd.Timestamp(v).tz_convert('UTC'):i for i,v in enumerate(data.timestamp)}; atr=np.asarray(features['atr_14'],float); rows=[]
    for tr in result.trades:
        en=pd.Timestamp(tr['entry_time']); en=en.tz_localize('UTC') if en.tzinfo is None else en.tz_convert('UTC'); ex=pd.Timestamp(tr['exit_time']); ex=ex.tz_localize('UTC') if ex.tzinfo is None else ex.tz_convert('UTC')
        if en not in ts or ts[en]<1: continue
        i=ts[en]; ep=float(data.open.iloc[i]); sd=float(atr[i-1]*strategy.stop_atr); sign=1 if tr['direction']=='LONG' else -1
        rows.append({'strategy_id':strategy.readable_id,'market':market,'timeframe':timeframe,'direction':tr['direction'],'entry_timestamp':en,'exit_timestamp':ex,'entry_price':ep,'stop_distance':sd,'stop_price':ep-sd if sign>0 else ep+sd,'net_R':float(tr['r'])})
    return pd.DataFrame(rows)

def accepted(events,members,risk=.005,cap=.02):
    frames=[]; w=1/max(1,len(members))
    for sid in members:
        q=events[events.strategy_id==sid].copy()
        if len(q): q['allocated_risk']=risk*w; frames.append(q)
    if not frames:return pd.DataFrame()
    x=pd.concat(frames,ignore_index=True).sort_values(['entry_timestamp','strategy_id','exit_timestamp']); active=[]; keep=[]
    for r in x.itertuples(index=False):
        active=[a for a in active if a.exit_timestamp>r.entry_timestamp]
        if sum(float(a.allocated_risk) for a in active)+float(r.allocated_risk)<=cap+1e-12: keep.append(r); active.append(r)
    return pd.DataFrame(keep)

def make_candidates(data,market,timeframe,seed,n):
    features=prepare_features(data,grammar_version='v1.7'); ev=FastEvaluator(data,features,initial_capital=10000,spread=.0001,slippage=.00002,cache_size=256,engine='auto'); gen=GeneticGenerator(market,timeframe,seed=seed,max_predicates=4,min_predicates=1,population_size=40,mutation_rate=.35,crossover_rate=.70,mode='scale'); rows=[]; results=[]; seen=set(); attempts=0
    while len(rows)<n and attempts<n*20:
        attempts+=1; s=gen.ask(known_hashes=seen)
        if s.canonical_hash in seen: continue
        seen.add(s.canonical_hash); r=ev.evaluate(s,rich=False); gen.tell(s,r)
        gate=strategy_gate(r.profit_factor,r.trade_count)
        rows.append({'strategy_id':s.readable_id,'canonical_hash':s.canonical_hash,'market':market,'timeframe':timeframe,'direction':s.direction,'net_pf':r.profit_factor,'trades':r.trade_count,'expectancy_R':r.expectancy_r,'max_dd':r.max_drawdown,'gate_pass':gate['pass'],'strategy_json':s.to_json()}); results.append((s,r))
    metrics=pd.DataFrame(rows); gated=metrics[metrics.gate_pass].copy(); gated=gated.sort_values(['net_pf','expectancy_R','trades','canonical_hash'],ascending=[False,False,False,True]).head(20); chosen=[]; ledgers=[]
    for row in gated.itertuples(index=False):
        s=next(a for a,b in results if a.readable_id==row.strategy_id); rr=ev.evaluate(s,rich=True); ledger=event_ledger(s,rr,data,features,market,timeframe); chosen.append(row.strategy_id); ledgers.append(ledger)
        if len(chosen)>=10: break
    return metrics,pd.concat(ledgers,ignore_index=True) if ledgers else pd.DataFrame(),chosen,{'attempts':attempts,'unique':len(rows),'duplicates':attempts-len(rows),'generator_telemetry':gen.telemetry}

def portfolio_members(events,ids):
    if len(ids)<=10:return ids
    return ids[:10]

def run_cycle(cycle,market='EURUSD',timeframe='H1',seed=None,n=1000):
    mpath=DATA[(market,timeframe)]; fpath=DATA[(market,'M15')]; raw=load_ohlcv(mpath); forward=load_ohlcv(fpath)
    ms=pd.Timestamp(cycle.manufacture_start,tz='UTC'); me=pd.Timestamp(cycle.manufacture_end,tz='UTC'); fs=pd.Timestamp(cycle.forward_start,tz='UTC'); fe=pd.Timestamp(cycle.forward_end,tz='UTC')
    manufacture=raw[(raw.timestamp>=ms)&(raw.timestamp<me)].reset_index(drop=True); forward_h1=raw[(raw.timestamp>=fs)&(raw.timestamp<fe)].reset_index(drop=True); forward_m15=forward[(forward.timestamp>=fs)&(forward.timestamp<fe)].reset_index(drop=True)
    if len(manufacture)==0 or len(forward_h1)==0:return {'status':'NO_DATA','forward_year':cycle.forward_year}
    metrics,events,ids,telemetry=make_candidates(manufacture,market,timeframe,seed or 9000+cycle.forward_year,n)
    lib_hash=hashlib.sha256('|'.join(sorted(metrics.canonical_hash)).encode()).hexdigest(); members=portfolio_members(events,ids); port_hash=hashlib.sha256('|'.join(sorted(members)).encode()).hexdigest()
    # Selection is frozen before any Forward evaluation.  Forward events are
    # reconstructed only after this manifest is persisted conceptually.
    write(f'cycle_{market}_{timeframe}_{cycle.forward_year}_freeze.json',{'forward_year':cycle.forward_year,'market':market,'timeframe':timeframe,'library_hash':lib_hash,'portfolio_hash':port_hash,'members':members,'risk':.005,'max_open_risk':.02,'status':'PORTFOLIO_FROZEN','manufacture_end':str(me),'forward_start':str(fs),'oos_accesses':0})
    features=prepare_features(forward_h1,grammar_version='v1.7'); ev=FastEvaluator(forward_h1,features,initial_capital=10000,spread=.0001,slippage=.00002,cache_size=0,engine='auto'); forward_parts=[]
    for row in metrics[metrics.strategy_id.isin(members)].itertuples(index=False):
        from sqx_engine.strategy import StrategyDefinition
        s=StrategyDefinition.from_json(row.strategy_json); rr=ev.evaluate(s,rich=True); forward_parts.append(event_ledger(s,rr,forward_h1,features,market,timeframe))
    f_events=pd.concat(forward_parts,ignore_index=True) if forward_parts else pd.DataFrame(); f_events=f_events[(f_events.entry_timestamp>=fs)&(f_events.entry_timestamp<fe)] if len(f_events) else f_events
    bars={market:forward_m15}; e=accepted(f_events,members,.005,.02); evaluator=CurrentFtmoEvaluator(ftmo_2step_current_profile(.10)); ch=evaluator.evaluate(e,bars,fs,fe)
    verification=None
    if ch['status']=='PASS' and ch['pass_timestamp'] is not None:
        vstart=ch['pass_timestamp']; verification=CurrentFtmoEvaluator(ftmo_2step_current_profile(.05)).evaluate(e,bars,vstart,fe)
    return {'status':'COMPLETE','forward_year':cycle.forward_year,'strategy_metrics':metrics,'library_size':int(metrics.gate_pass.sum()),'generated':len(metrics),'trade_gate':int((metrics.trades>250).sum()),'portfolio_size':len(members),'members':members,'portfolio_hash':port_hash,'library_hash':lib_hash,'challenge':{k:v for k,v in ch.items() if k!='telemetry'},'verification':{k:v for k,v in verification.items() if k!='telemetry'} if verification else None,'funded':bool(verification and verification['status']=='PASS'),'forward_events':int(len(e)),'telemetry':telemetry,'manufacture_window':{'start':str(ms),'end':str(me)},'forward_window':{'start':str(fs),'end':str(fe)},'oos_accesses':0}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--pilot',action='store_true'); ap.add_argument('--all-h1',action='store_true'); ap.add_argument('--n',type=int,default=1000); a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True); started=time.perf_counter()
    # The earliest supported raw OHLC starts on 2003-05-05.  January 2003
    # would create an incomplete first manufacture window and is forbidden.
    cycles=rolling_cycles('2003-05-05','2026-04-14',5,1,1,False); selected=[c for c in cycles if c.forward_year in ([2009,2014,2019] if a.pilot else [c.forward_year for c in cycles])]
    cells=[('EURUSD','H1')] if a.pilot else ([('EURUSD','H1'),('GBPUSD','H1'),('NZDUSD','H1'),('USDCAD','H1'),('USDCHF','H1'),('USDJPY','H1'),('XAUUSD','H1')] if a.all_h1 else [('EURUSD','H1')])
    rows=[]; strategy_rows=[]
    for market,timeframe in cells:
        for c in selected:
            result=run_cycle(c,market,timeframe,9000+c.forward_year,a.n); result['market']=market; result['timeframe']=timeframe; rows.append({k:v for k,v in result.items() if k not in ('strategy_metrics','telemetry')});
            if 'strategy_metrics' in result:
                q=result['strategy_metrics'].copy(); q['forward_year']=c.forward_year; q['market']=market; q['timeframe']=timeframe; strategy_rows.append(q)
            print(json.dumps({'market':market,'forward_year':c.forward_year,'generated':result.get('generated'),'library_size':result.get('library_size'),'challenge':result.get('challenge',{}).get('status'),'funded':result.get('funded')},default=str),flush=True)
    if strategy_rows: pd.concat(strategy_rows,ignore_index=True).to_parquet(OUT/'cycle_strategy_metrics.parquet',index=False)
    pd.DataFrame(rows).to_json(OUT/'ftmo_forward_results.json',orient='records',indent=2)
    write('cycle_manifest.json',{'cycles':[c.to_dict() for c in selected],'cells':cells,'n':a.n,'oos_accesses':0})
    write('rolling_factory_summary.json',{'mode':'PILOT' if a.pilot else 'ALL_H1','cycles':len(rows),'results':[{k:v for k,v in r.items() if k in ('forward_year','market','timeframe','generated','library_size','portfolio_size','challenge','verification','funded','oos_accesses')} for r in rows],'runtime_seconds':time.perf_counter()-started,'oos_accesses':0})
    write('performance.json',{'runtime_seconds':time.perf_counter()-started,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'cycles':len(rows),'oos_accesses':0})
    print(json.dumps({'cycles':len(rows),'runtime_seconds':time.perf_counter()-started,'oos_accesses':0},indent=2))

if __name__=='__main__': main()
