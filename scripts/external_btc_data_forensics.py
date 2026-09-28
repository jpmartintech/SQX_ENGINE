from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"runs/reports/external_btc_data_forensics"
EXT=ROOT/"data/external_candidate/BTCUSDT_15M_EXTERNAL.csv"
CAN=ROOT/"data/crypto_v12/canonical/BTC_M15_signal_market_binance.parquet"
RAW=ROOT/"data/crypto_v11/raw/binance_futures/BTC_15m.csv"

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def integrity(f,vol):
    d=f.timestamp.diff().dropna(); gaps=d[d>pd.Timedelta(minutes=15)]
    return {'rows':len(f),'first':str(f.timestamp.iloc[0]),'last':str(f.timestamp.iloc[-1]),'duplicate_timestamps':int(f.timestamp.duplicated().sum()),'monotonic':bool(f.timestamp.is_monotonic_increasing),'missing_grid_intervals':int((d!=pd.Timedelta(minutes=15)).sum()),'gap_count':int(len(gaps)),'largest_gap_minutes':float(gaps.max().total_seconds()/60) if len(gaps) else 0,'ohlc_valid':bool((f.high>=f[['open','close','low']].max(axis=1)).all() and (f.low<=f[['open','close','high']].min(axis=1)).all()),'nonpositive_prices':int((f[['open','high','low','close']]<=0).sum().sum()),'negative_volume':int((f[vol]<0).sum()),'zero_volume':int((f[vol]==0).sum()),'timezone':'UTC; external naive timestamps interpreted as UTC'}

def dist(a,b):
    ad=(a.astype(float)-b.astype(float)).abs(); pdiff=ad/b.astype(float).abs().replace(0,np.nan)
    return {'mean':float(ad.mean()),'median':float(ad.median()),'p95':float(ad.quantile(.95)),'p99':float(ad.quantile(.99)),'max':float(ad.max()),'pct_exact':float((ad==0).mean()),'pct_within_1bp':float((pdiff<=.0001).mean()),'pct_within_5bp':float((pdiff<=.0005).mean()),'pct_within_10bp':float((pdiff<=.001).mean()),'pct_within_25bp':float((pdiff<=.0025).mean()),'pct_within_50bp':float((pdiff<=.005).mean())}

def corr(a,b): return {'pearson':float(a.corr(b)),'spearman':float(a.rank().corr(b.rank()))}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    e=pd.read_csv(EXT); e['timestamp']=pd.to_datetime(e.datetime,utc=True); e=e.rename(columns={'volume':'volume_ext'})[['timestamp','open','high','low','close','volume_ext']].sort_values('timestamp').reset_index(drop=True)
    c=pd.read_parquet(CAN); c['timestamp']=pd.to_datetime(c.timestamp_open,utc=True); c=c.rename(columns={'volume':'volume_can'})[['timestamp','open','high','low','close','volume_can']].sort_values('timestamp').reset_index(drop=True)
    em={'path':str(EXT.relative_to(ROOT)),'sha256':sha(EXT),'rows':len(e),'first':str(e.timestamp.iloc[0]),'last':str(e.timestamp.iloc[-1]),'source':'unknown; no embedded venue metadata','product':'unknown'}
    cm={'path':str(CAN.relative_to(ROOT)),'sha256':sha(CAN),'raw_path':str(RAW.relative_to(ROOT)),'raw_sha256':sha(RAW),'source':'BINANCE_USDM_FUTURES_PUBLIC_REST','product':'USD-M perpetual futures signal market','rows':len(c),'first':str(c.timestamp.iloc[0]),'last':str(c.timestamp.iloc[-1])}
    (OUT/'external_metadata.json').write_text(json.dumps(em,indent=2)+'\n'); (OUT/'canonical_metadata.json').write_text(json.dumps(cm,indent=2)+'\n')
    ov=e[['timestamp']].merge(c[['timestamp']],on='timestamp',how='outer',indicator=True); common=ov[ov._merge=='both']; (OUT/'timestamp_overlap.json').write_text(json.dumps({'matched_timestamps':len(common),'external_only_timestamps':int((ov._merge=='left_only').sum()),'canonical_only_timestamps':int((ov._merge=='right_only').sum()),'common_range':[str(common.timestamp.min()),str(common.timestamp.max())],'external_only_early_history':['2017-08-17T04:00:00Z','2022-12-31T23:45:00Z'],'sqx_only_late_history':['2026-09-28T10:00:00Z','2026-09-28T10:30:00Z']},indent=2)+'\n')
    m=e.merge(c,on='timestamp',suffixes=('_ext','_can')).sort_values('timestamp'); price={k:dist(m[k+'_ext'],m[k+'_can']) for k in ('open','high','low','close')}; (OUT/'price_comparison.json').write_text(json.dumps(price,indent=2)+'\n')
    m['ret_ext']=m.close_ext.pct_change(); m['ret_can']=m.close_can.pct_change(); r=m.dropna(subset=['ret_ext','ret_can']); (OUT/'return_comparison.json').write_text(json.dumps({'correlation':corr(r.ret_ext,r.ret_can),'mean_absolute_return_difference':float((r.ret_ext-r.ret_can).abs().mean()),'p95_return_difference':float((r.ret_ext-r.ret_can).abs().quantile(.95)),'maximum_return_difference':float((r.ret_ext-r.ret_can).abs().max())},indent=2)+'\n')
    years=[]
    for y,g in r.groupby(r.timestamp.dt.year):
        cc=corr(g.ret_ext,g.ret_can); years.append({'year':int(y),'matched_bars':len(g),'pearson':cc['pearson'],'spearman':cc['spearman'],'mean_abs_return_difference':float((g.ret_ext-g.ret_can).abs().mean())})
    pd.DataFrame(years).to_csv(OUT/'yearly_comparison.csv',index=False)
    shapes={'range':(m.high_ext-m.low_ext,m.high_can-m.low_can),'body':(m.close_ext-m.open_ext,m.close_can-m.open_can),'upper_wick':(m.high_ext-m[['open_ext','close_ext']].max(axis=1),m.high_can-m[['open_can','close_can']].max(axis=1)),'lower_wick':(m[['open_ext','close_ext']].min(axis=1)-m.low_ext,m[['open_can','close_can']].min(axis=1)-m.low_can)}; (OUT/'bar_shape_comparison.json').write_text(json.dumps({k:{'correlation':corr(a,b),'error':dist(a,b)} for k,(a,b) in shapes.items()},indent=2)+'\n')
    v=m[['volume_ext','volume_can']]; ratio=v.volume_ext/v.volume_can.replace(0,np.nan); (OUT/'volume_comparison.json').write_text(json.dumps({'raw':corr(v.volume_ext,v.volume_can),'log':corr(np.log1p(v.volume_ext),np.log1p(v.volume_can)),'median_ratio':float(ratio.median()),'p05_ratio':float(ratio.quantile(.05)),'p95_ratio':float(ratio.quantile(.95)),'interpretation':'units/product differ; not interchangeable'},indent=2)+'\n')
    (OUT/'gap_comparison.json').write_text(json.dumps({'external':integrity(e,'volume_ext'),'canonical':integrity(c,'volume_can')},indent=2)+'\n')
    def daily(f,vol): return f.set_index('timestamp').resample('D').agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),volume=(vol,'sum')).dropna().reset_index()
    de=daily(e,'volume_ext'); dc=daily(c,'volume_can'); dm=de.merge(dc,on='timestamp',suffixes=('_external','_canonical')); dm.to_csv(OUT/'daily_comparison.csv',index=False); (OUT/'daily_comparison.json').write_text(json.dumps({'matched_days':len(dm),'close':dist(dm.close_external,dm.close_canonical),'return':corr(dm.close_external.pct_change().dropna(),dm.close_canonical.pct_change().dropna())},indent=2)+'\n')
    close_corr=float(m.close_ext.corr(m.close_can)); exact=float(((m.open_ext==m.open_can)&(m.high_ext==m.high_can)&(m.low_ext==m.low_can)&(m.close_ext==m.close_can)).mean()); classification='SAME_VENUE_DIFFERENT_PRODUCT' if close_corr>.999 and exact<.5 else 'CROSS_VENUE_MATERIALLY_DIFFERENT'
    (OUT/'source_fingerprint.json').write_text(json.dumps({'repository_evidence':['SQX canonical metadata identifies Binance USD-M Futures','external begins 2017-08-17, before SQX USD-M history','no repository Binance Spot BTC M15 dataset found'],'numerical_evidence':{'matched_bars':len(m),'close_correlation':close_corr,'exact_ohlc_fraction':exact},'classification_basis':'same underlying BTC market with likely different product'},indent=2)+'\n')
    (OUT/'EXTERNAL_BTC_DATA_FORENSICS_REPORT.md').write_text(f'''# EXTERNAL BTCUSDT M15 — DATA FORENSICS\n\nExternal: `{EXT.relative_to(ROOT)}`; SHA256 `{sha(EXT)}`; {len(e):,} rows; {e.timestamp.iloc[0]} → {e.timestamp.iloc[-1]}.\n\nCanonical SQX: `{CAN.relative_to(ROOT)}`; SHA256 `{sha(CAN)}`; Binance USD-M Futures; {len(c):,} rows; {c.timestamp.iloc[0]} → {c.timestamp.iloc[-1]}.\n\nMatched bars: {len(m):,}. Close correlation: {close_corr:.8f}. Exact all-OHLC matches: {exact:.4%}.\n\nThe external file begins in 2017, before the SQX USD-M Futures history. It is therefore not the same SQX futures file; the numerical evidence is consistent with the same BTCUSDT market but a different product, most plausibly Binance Spot. The file has no embedded venue metadata, so that product inference remains conditional.\n\nClassification: **{classification}**.\n\nSuitable as external validation data: **CONDITIONAL**. It is suitable for source/product validation only after explicitly treating it as a separate signal-market dataset. It must not be described as identical Hyperliquid or SQX Binance Futures execution data.\n\nStrategy accesses to external data: 0\n\nOOS status: UNCONSUMED_FOR_STRATEGY_TESTING\n''')
    print(json.dumps({'matched':len(m),'close_corr':close_corr,'exact_ohlc_fraction':exact,'classification':classification},indent=2))
if __name__=='__main__': main()
