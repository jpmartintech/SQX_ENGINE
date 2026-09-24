"""PRODUCTION_01 data audit and configuration only; frozen engine imports."""
from pathlib import Path
import json, hashlib, collections
import pandas as pd
import numpy as np
from sqx_engine.data.catalog import MARKETS, TIMEFRAMES, DataCatalog, resample_closed
from sqx_engine.data.split import file_sha256
from sqx_engine.production import atomic_json
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'runs/reports/production_01'
SOURCE=Path('/home/xaume/proyectos/sqx_lite/data')

def read_source(path):
    f=pd.read_csv(path); f.columns=f.columns.str.lower()
    if 'date' in f and 'time' in f:
        f['timestamp']=pd.to_datetime(f['date'].astype(str)+' '+f['time'],format='%Y%m%d %H:%M:%S',utc=True,errors='coerce')
    elif 'datetime' in f: f['timestamp']=pd.to_datetime(f.datetime,utc=True,errors='coerce')
    elif 'timestamp' in f: f['timestamp']=pd.to_datetime(f.timestamp,utc=True,errors='coerce')
    for c in ['open','high','low','close','volume']: f[c]=pd.to_numeric(f[c],errors='coerce')
    return f[['timestamp','open','high','low','close','volume']]

def audit(f,path,market,tf):
    t=f.timestamp; d=t.diff().dt.total_seconds()/60; minutes=TIMEFRAMES[tf]
    bad=((f.high<f[['open','close']].max(axis=1))|(f.low>f[['open','close']].min(axis=1))|(f.high<f.low))
    gaps=f.loc[d>minutes,['timestamp']].copy(); gaps['gap_minutes']=d[d>minutes]; gaps['previous_timestamp']=t.shift()[d>minutes]
    nan={c:int(v) for c,v in f.isna().sum().items()}
    invalid=bool(any(nan.values()) or t.duplicated().any() or not t.is_monotonic_increasing or bad.any() or not np.isfinite(f.drop(columns='timestamp')).all().all() or (d.dropna()<minutes).any())
    return dict(market=market,timeframe=tf,path=str(path),sha256=file_sha256(path),rows=len(f),start=str(t.min()),end=str(t.max()),chronological=bool(t.is_monotonic_increasing),duplicates=int(t.duplicated().sum()),NaN=nan,ohlc_violations=int(bad.sum()),spacing_minutes={str(k):int(v) for k,v in d.value_counts().items()},gap_count=len(gaps),max_gap_minutes=float(d.max()),missing_grid_slots=int(((d[d>minutes]/minutes)-1).sum()),gap_note='Includes closed-market weekends and holidays; no bars fabricated',status='DATASET_INVALID' if invalid else 'DATASET_AVAILABLE'),gaps

if __name__=='__main__':
    REPORT.mkdir(parents=True,exist_ok=True)
    audits=[]; rows=[]; catalog=DataCatalog(ROOT); now=pd.Timestamp.now(tz='UTC').isoformat()
    for market in MARKETS:
        src=SOURCE/f'{market}_15M.csv'
        if not src.exists(): continue
        f=read_source(src); a,gaps=audit(f,src,market,'M15'); audits.append(a)
        gaps.to_csv(REPORT/f'{market}_M15_gaps.csv',index=False)
        atomic_json(REPORT/'source_audits.json',[r for r in audits if r['timeframe']=='M15'])
        print(market,a['status'],len(f),a['start'],a['end'],'OHLC',a['ohlc_violations'],flush=True)
        if a['status']!='DATASET_AVAILABLE': continue
        target=ROOT/'data/cloud'/f'{market}_M15.csv'
        content=f.to_csv(index=False)
        if target.exists(): assert target.read_text()==content
        else: target.write_text(content)
        native=catalog._audit(target,market,'M15')
        native['provenance']={'source_path':str(src),'source_sha256':a['sha256'],'method':'schema_only_Date_Time_to_timestamp_no_price_changes','created_at':now,'timezone_note':'Naive source labels preserved under existing V1.8 UTC bar-open convention; no offset applied'}
        rows.append(native)
        for tf in ['H1','H4']:
            derived=resample_closed(f,'M15',tf,now)
            target=ROOT/'data/derived'/f'{market}_{tf}_{native["sha256"][:12]}_{len(derived)}.csv'
            target.parent.mkdir(parents=True,exist_ok=True)
            content=derived.to_csv(index=False)
            if target.exists(): assert target.read_text()==content
            else: target.write_text(content)
            prov={'source_path':native['path'],'source_timeframe':'M15','source_sha256':native['sha256'],'method':'complete_utc_open_buckets_v1','available_through':str(derived.available_at.iloc[-1]),'created_at':now}
            row=catalog._audit(target,market,tf,'derived',prov); rows.append(row)
            da,dg=audit(derived[['timestamp','open','high','low','close','volume']],target,market,tf)
            audits.append(da)
            dg.to_csv(REPORT/f'{market}_{tf}_gaps.csv',index=False)
    atomic_json(REPORT/'dataset_audits.json',audits)
    assert all(r['status']=='DATASET_AVAILABLE' for r in rows), 'Integrity errors: do not produce'
    # Keep the immutable native EURUSD H1 golden dataset as selected production baseline.
    # Its newly derived M15->H1 alternate remains audited and referenced in this report.
    baseline=catalog._audit(ROOT/'data/cloud/EURUSD_1H.csv','EURUSD','H1')
    rows=[baseline if (r['market'],r['timeframe'])==('EURUSD','H1') else r for r in rows]
    atomic_json(ROOT/'data/catalog.json',{'schema_version':1,'datasets':rows})
    atomic_json(REPORT/'catalog.json',{'schema_version':1,'datasets':rows})
