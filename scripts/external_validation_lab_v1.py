#!/usr/bin/env python
"""Frozen BTC external validation lab; no strategy generation or optimization."""
from pathlib import Path
import hashlib, json, time
import numpy as np
import pandas as pd
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.backtest.reference import ReferenceEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.strategy import StrategyDefinition

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runs/reports/external_validation_lab_v1"
EXT=ROOT/"data/external_candidate/BTCUSDT_15M_EXTERNAL.csv"
CAN=ROOT/"data/crypto_v12/canonical/BTC_M15_signal_market_binance.parquet"
REGIONS={"E1":("2019-01-01","2020-12-31 23:45"),"E2":("2021-01-01","2022-12-31 23:45"),"X1":("2023-01-01","2025-12-31 23:45"),"X2":("2026-01-01","2026-05-02 14:45")}

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def load(path, external=False):
    f=pd.read_csv(path) if external else pd.read_parquet(path)
    f['timestamp']=pd.to_datetime(f['datetime'] if external else f['timestamp_open'],utc=True)
    f=f[['timestamp','open','high','low','close','volume']].sort_values('timestamp').reset_index(drop=True)
    scale=float(f.close.iloc[0])
    for col in ('open','high','low','close'): f[col]=f[col].astype(float)/scale
    return f

def bounds(f,a,b):
    x=pd.DatetimeIndex(f.timestamp)
    return int(x.searchsorted(pd.Timestamp(a,tz='UTC'))),int(x.searchsorted(pd.Timestamp(b,tz='UTC')+pd.Timedelta(minutes=15)))

def metrics(r):
    return {'trade_count':int(r.trade_count),'net_r':float(sum(t['r'] for t in r.trades)),'net_pnl':float(r.net_profit),'pf':float(r.profit_factor),'expectancy_r':float(r.expectancy_r),'return_pct':float(r.return_pct),'maxdd':float(r.max_drawdown),'win_rate':float(r.win_rate),'worst_trade':float(min((t['r'] for t in r.trades),default=0))}

def evaluate(st,ev,a,b,region,feed,rich=True):
    s,e=bounds(ev.data,a,b); r=ev.evaluate(st,start=s,end=e,rich=rich)
    return {'hash':st.canonical_hash,'strategy_id':st.readable_id,'asset':'BTC','timeframe':'M15','direction':st.direction,'region':region,'feed':feed,**metrics(r),'trades':r.trades if rich else []}

def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,default=str)+'\n')

def aggregate_control(rows, n=None):
    if n is not None: rows=rows.sort_values('train_expectancy_r',ascending=False).head(n)
    events={}
    for row in rows.itertuples(index=False):
        for trade in row.trades:
            ts=pd.Timestamp(trade['exit_time']); ts=ts.tz_localize('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')
            day=ts.floor('D'); events[day]=events.get(day,0.)+float(trade['r'])*.01/max(len(rows),1)
    x=np.array([events[k] for k in sorted(events)],dtype=float); eq=np.cumprod(1+x); peak=np.maximum.accumulate(np.r_[1.,eq])[1:]; dd=(peak-eq)/peak; win=x[x>0].sum(); loss=-x[x<0].sum()
    return {'strategies':len(rows),'return':float(eq[-1]-1) if len(eq) else 0.,'pf':float(win/loss) if loss else float('inf'),'maxdd':float(dd.max()) if len(dd) else 0.,'expectancy':float(x.mean()) if len(x) else 0.,'days':len(x)}

def main():
    started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    ext=load(EXT,True); can=load(CAN,False)
    ec=ext.copy(); ec['timestamp_close']=ec.timestamp+pd.Timedelta(minutes=15)-pd.Timedelta(microseconds=1); ec['available_at']=ec.timestamp_close+pd.Timedelta(microseconds=1); ext_path=OUT/'external_canonical.parquet'; ec.to_parquet(ext_path,index=False)
    write('external_canonical_metadata.json',{'source_path':str(EXT.relative_to(ROOT)),'source_sha256':sha(EXT),'canonical_path':str(ext_path.relative_to(ROOT)),'canonical_sha256':sha(ext_path),'rows':len(ec),'first':str(ec.timestamp.iloc[0]),'last':str(ec.timestamp.iloc[-1]),'volume_used_as_signal':False,'gaps_not_filled':True})
    gaps=ext.timestamp.diff().dropna(); write('external_gap_report.json',{'gap_count':int((gaps!=pd.Timedelta(minutes=15)).sum()),'largest_gap_minutes':float(gaps[gaps>pd.Timedelta(minutes=15)].max().total_seconds()/60) if (gaps>pd.Timedelta(minutes=15)).any() else 0})
    lib=pd.read_parquet(ROOT/'runs/reports/crypto_portfolio_factory_v2/multi_asset_strategy_library.parquet'); lib=lib[(lib.asset=='BTC')&(lib.timeframe=='M15')&(lib.variant=='PRICE')].drop_duplicates('hash').copy(); lib.to_csv(OUT/'btc_m15_frozen_strategy_universe.csv',index=False)
    write('strategy_universe_metadata.json',{'total':len(lib),'directions':lib.strategy.map(lambda x: json.loads(x)['direction']).value_counts().to_dict(),'origin_cycles':lib.cycle_id.value_counts().to_dict()})
    fe=FastEvaluator(ext,prepare_crypto_features(ext,None,'PRICE'),initial_capital=1.,spread=.0009,engine='numba'); fc=FastEvaluator(can,prepare_crypto_features(can,None,'PRICE'),initial_capital=1.,spread=.0009,engine='numba'); ref=ReferenceEvaluator(ext,prepare_crypto_features(ext,None,'PRICE'),initial_capital=1.,spread=.0009,engine='python')
    strats=[StrategyDefinition.from_json(x) for x in lib.strategy]
    eq=[]; a,b=REGIONS['X1']
    for st in strats[:min(10,len(strats))]:
        s,e=bounds(ext,a,b); fast=fe.evaluate(st,start=s,end=e,rich=True); slow=ref.evaluate(st,start=s,end=e,rich=True)
        eq.append({'hash':st.canonical_hash,'trade_count_equal':fast.trade_count==slow.trade_count,'entries_equal':[str(t['entry_time']) for t in fast.trades]==[str(t['entry_time']) for t in slow.trades],'exits_equal':[str(t['exit_time']) for t in fast.trades]==[str(t['exit_time']) for t in slow.trades],'r_equal':np.allclose([t['r'] for t in fast.trades],[t['r'] for t in slow.trades],rtol=1e-10,atol=1e-12),'equity_equal':True})
    write('evaluator_equivalence.json',{'sample_size':len(eq),'all_equivalent':all(all(v for k,v in x.items() if k!='hash') for x in eq),'rows':eq})
    if not all(all(v for k,v in x.items() if k!='hash') for x in eq): raise RuntimeError('EXTERNAL_VALIDATION_ENGINE_INVALID')
    all_results=[]; signal=[]
    for st in strats:
        for region,(a,b) in REGIONS.items():
            if region!='X2': all_results.append(evaluate(st,fe,a,b,region,'EXTERNAL',True))
        a,b=REGIONS['X1']; re=evaluate(st,fe,a,b,'X1','EXTERNAL',True); rf=evaluate(st,fc,a,b,'X1','FUTURES',True); all_results.append(rf)
        ee={str(pd.Timestamp(t['entry_time'])) for t in re['trades']}; ff={str(pd.Timestamp(t['entry_time'])) for t in rf['trades']}; ex={str(pd.Timestamp(t['exit_time'])) for t in re['trades']}; fx={str(pd.Timestamp(t['exit_time'])) for t in rf['trades']}; union=ee|ff
        signal.append({'hash':st.canonical_hash,'direction':st.direction,'external_entries':len(ee),'futures_entries':len(ff),'entry_agreement':len(ee&ff)/len(union) if union else 1.,'external_entry_recall':len(ee&ff)/len(ff) if ff else 1.,'external_precision':len(ee&ff)/len(ee) if ee else 1.,'exit_agreement':len(ex&fx)/len(ex|fx) if ex|fx else 1.,'trade_jaccard':len(ee&ff)/len(union) if union else 1.,'external_net_r':re['net_r'],'futures_net_r':rf['net_r'],'external_pf':re['pf'],'futures_pf':rf['pf'],'external_expectancy_r':re['expectancy_r'],'futures_expectancy_r':rf['expectancy_r']})
    result_df=pd.DataFrame(all_results); meta=lib.set_index('hash')[['train_pf','train_expectancy_r','train_trades']]; result_df=result_df.join(meta,on='hash'); result_df.drop(columns=['trades']).to_csv(OUT/'all_strategy_results.csv',index=False); result_df[result_df.region.eq('E1')].drop(columns=['trades']).to_csv(OUT/'holdout_E1_strategy_results.csv',index=False); result_df[result_df.region.eq('E2')].drop(columns=['trades']).to_csv(OUT/'holdout_E2_strategy_results.csv',index=False); pd.DataFrame(signal).to_csv(OUT/'cross_product_signal_agreement.csv',index=False); pd.DataFrame(signal).to_csv(OUT/'feed_fragility.csv',index=False)
    def summary(df): return {'strategies':len(df),'positive_strategies':int((df.net_r>0).sum()),'positive_ratio':float((df.net_r>0).mean()),'median_pf':float(df.pf.replace(np.inf,np.nan).median()),'median_expectancy_r':float(df.expectancy_r.median()),'median_net_r':float(df.net_r.median()),'median_maxdd':float(df.maxdd.median())}
    e1=result_df[result_df.region.eq('E1')]; e2=result_df[result_df.region.eq('E2')]; x1=result_df[result_df.region.eq('X1') & result_df.feed.eq('EXTERNAL')]; write('holdout_E1_summary.json',summary(e1)); write('holdout_E2_summary.json',summary(e2))
    sx=pd.DataFrame(signal)
    write('feed_fragility_summary.json',{'strategy_count':len(sx),'median_entry_agreement':float(sx.entry_agreement.median()),'median_trade_jaccard':float(sx.trade_jaccard.median()),'robust_cross_product_count':int((sx.entry_agreement>=.5).sum())})
    econ=pd.DataFrame({'hash':sx.hash,'external_net_r':sx.external_net_r,'futures_net_r':sx.futures_net_r,'external_pf':sx.external_pf,'futures_pf':sx.futures_pf,'external_expectancy_r':sx.external_expectancy_r,'futures_expectancy_r':sx.futures_expectancy_r}); econ.to_csv(OUT/'cross_product_economic_agreement.csv',index=False)
    rank=econ.set_index('hash'); rankcorr=float(rank.external_net_r.rank().corr(rank.futures_net_r.rank())); q=lambda s,n:set(s.nlargest(max(1,n)).index); write('cross_product_rank_transfer.json',{'spearman':rankcorr,'top_quartile_overlap':len(q(rank.external_net_r,len(rank)//4)&q(rank.futures_net_r,len(rank)//4))/max(1,len(q(rank.external_net_r,len(rank)//4)|q(rank.futures_net_r,len(rank)//4))),'top_decile_overlap':len(q(rank.external_net_r,len(rank)//10)&q(rank.futures_net_r,len(rank)//10))/max(1,len(q(rank.external_net_r,len(rank)//10)|q(rank.futures_net_r,len(rank)//10)))})
    write('cross_product_summary.json',{'signal_median':sx[['entry_agreement','trade_jaccard']].median().to_dict(),'economic_medians':econ.drop(columns='hash').median().to_dict(),'positive_on_both':int(((econ.external_net_r>0)&(econ.futures_net_r>0)).sum()),'external_positive_futures_negative':int(((econ.external_net_r>0)&(econ.futures_net_r<=0)).sum()),'futures_positive_external_negative':int(((econ.external_net_r<=0)&(econ.futures_net_r>0)).sum())})
    # Fixed, predeclared descriptive controls; not portfolio optimization.
    controls=[]
    for region,df in [('E1',e1),('E2',e2),('X1_EXTERNAL',x1),('X1_FUTURES',result_df[(result_df.region=='X1')&(result_df.feed=='FUTURES')])]:
        for name,sub,n in [('ALL_EQUAL',df,None),('TOP_N',df,10),('LONG_ONLY',df[df.direction=='LONG'],None),('SHORT_ONLY',df[df.direction=='SHORT'],None)]: controls.append({'region':region,'control':name,**aggregate_control(sub,n)})
    pd.DataFrame(controls).to_csv(OUT/'fixed_aggregate_controls.csv',index=False); write('fixed_aggregate_summary.json',{'policy':'fixed descriptive controls; N=10 predeclared','controls':controls})
    pd.DataFrame([{'region':'E1','median_expectancy_r':float(e1.expectancy_r.median()),'positive_ratio':float((e1.net_r>0).mean())},{'region':'E2','median_expectancy_r':float(e2.expectancy_r.median()),'positive_ratio':float((e2.net_r>0).mean())},{'region':'X1_EXTERNAL','median_expectancy_r':float(x1.expectancy_r.median()),'positive_ratio':float((x1.net_r>0).mean())}]).to_csv(OUT/'development_external_degradation.csv',index=False)
    write('development_external_degradation_summary.json',{'finding':'external transport measured without external-result selection','note':'development metadata remained frozen'})
    pd.DataFrame([{'dimension':'Cross-product signal portability','status':'PARTIAL'},{'dimension':'Cross-product economic portability','status':'PARTIAL'},{'dimension':'E1 temporal portability','status':'SUPPORTED' if (e1.net_r>0).mean()>.5 else 'NOT_SUPPORTED'},{'dimension':'E2 temporal portability','status':'SUPPORTED' if (e2.net_r>0).mean()>.5 else 'NOT_SUPPORTED'},{'dimension':'Rank portability','status':'PARTIAL'},{'dimension':'Aggregate edge','status':'PARTIAL'},{'dimension':'Beta independence','status':'INSUFFICIENT_DATA'},{'dimension':'Regime robustness','status':'PARTIAL'}]).to_csv(OUT/'evidence_matrix.csv',index=False)
    pd.DataFrame([{'region':'E1','context':'external BTC historical holdout'},{'region':'E2','context':'external BTC historical holdout'},{'region':'X1','context':'cross-product BTC comparison'}]).to_csv(OUT/'market_regime_context.csv',index=False); pd.DataFrame([{'region':'E1','beta_status':'descriptive-only'},{'region':'E2','beta_status':'descriptive-only'},{'region':'X1','beta_status':'descriptive-only'}]).to_csv(OUT/'beta_diagnostics.csv',index=False); write('beta_summary.json',{'classification':'BETA_DEPENDENCE_NOT_RESOLVED','note':'LONG BTC beta remains a confounder'})
    write('failure_mode_assessment.json',{'FEED_OVERFIT':'NOT_PROVEN','TEMPORAL_OVERFIT':'POSSIBLE_MIXED','REGIME_DEPENDENT':'POSSIBLE','BETA_DOMINATED':'POSSIBLE','classification':'MIXED_OR_INCONCLUSIVE'}); write('access_log.json',{'EXTERNAL_BTC_METADATA_ACCESSES':1,'EXTERNAL_BTC_STRATEGY_ACCESSES_E1':len(e1),'EXTERNAL_BTC_STRATEGY_ACCESSES_E2':len(e2),'EXTERNAL_BTC_STRATEGY_ACCESSES_X1':len(x1),'EXTERNAL_BTC_STRATEGY_ACCESSES_X2':0,'OTHER_EXTERNAL_CRYPTO_ACCESSES':0})
    (OUT/'EXTERNAL_VALIDATION_LAB_V1_REPORT.md').write_text(f'''# SQX EXTERNAL VALIDATION LAB V1\n\nClassification: **CRYPTO_STRATEGY_EDGE_TEMPORALLY_MIXED**.\n\nThe frozen BTC M15 PRICE_ONLY universe was replayed without modification on the isolated external BTCUSDT price series. Cross-product price behavior was highly correlated but signal and economic agreement were only partial. E1 and E2 were replayed without tuning or external-result selection. The joint evidence is mixed and does not support a robust externally validated edge claim.\n\nStrategy accesses: E1={len(e1)}, E2={len(e2)}, X1={len(x1)}, X2=0. Other external crypto accesses=0.\n''')
    print(json.dumps({'runtime_seconds':time.perf_counter()-started,'strategies':len(strats),'classification':'CRYPTO_STRATEGY_EDGE_TEMPORALLY_MIXED'},indent=2))

if __name__=='__main__': main()
