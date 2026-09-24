"""Dataset registry and conservative closed-bar OHLCV resampling."""
from pathlib import Path
import json
import hashlib

import pandas as pd

from .split import audit_dataset, file_sha256

MARKETS = ('EURUSD', 'GBPUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY', 'XAUUSD')
TIMEFRAMES = {'M15': 15, 'H1': 60, 'H4': 240}
ALIASES = {'M15': ('M15', '15M', '15MIN'), 'H1': ('H1', '1H'), 'H4': ('H4', '4H')}


def resample_closed(frame, source_timeframe, timeframe, as_of):
    """Input/output timestamps are UTC bar opens; availability is bar close.

    Only exact, contiguous source-bar grids are retained. Incomplete leading,
    trailing and session-gap buckets are dropped, never filled or backdated.
    """
    source, target = TIMEFRAMES[source_timeframe], TIMEFRAMES[timeframe]
    if target <= source or target % source: raise ValueError('Cannot upsample or use non-integral timeframes')
    end = pd.Timestamp(as_of)
    end = end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
    f = frame.copy()
    f['timestamp'] = pd.to_datetime(f.timestamp, utc=True)
    if f.timestamp.duplicated().any() or not f.timestamp.is_monotonic_increasing: raise ValueError('Invalid source timestamps')
    if (f.timestamp.astype('datetime64[ns, UTC]').astype('int64') % (source * 60 * 10**9)).any(): raise ValueError('Source bars are not aligned')
    f = f[f.timestamp + pd.Timedelta(minutes=source) <= end]
    f['bucket'] = f.timestamp.dt.floor(f'{target}min')
    # Count + exact grid alignment + uniqueness imply a complete contiguous bucket.
    grouped = f.groupby('bucket', sort=True)
    result = grouped.agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
                         close=('close', 'last'), volume=('volume', 'sum'), count=('timestamp', 'size'))
    result = result[(result['count'] == target // source) & (result.index + pd.Timedelta(minutes=target) <= end)]
    result = result.drop(columns='count').reset_index().rename(columns={'bucket': 'timestamp'})
    result['available_at'] = result.timestamp + pd.Timedelta(minutes=target)
    return result


class DataCatalog:
    def __init__(self, root, path='data/catalog.json'):
        self.root = Path(root).resolve()
        self.path = self.root / path
        self.records = json.loads(self.path.read_text())['datasets'] if self.path.exists() else []

    def _audit(self, path, market, timeframe, kind='native', provenance=None, as_of=None):
        row = {'market': market, 'timeframe': timeframe, 'path': str(path.relative_to(self.root)),
               'kind': kind, 'source_timeframe': None if kind == 'native' else provenance['source_timeframe'],
               'timestamp_semantics': 'open', 'provenance': provenance or {}, 'status': 'DATASET_INVALID'}
        try:
            frame, audit = audit_dataset(path)
            minutes = TIMEFRAMES[timeframe]
            if (frame.timestamp.astype('datetime64[ns, UTC]').astype('int64') % (minutes * 60 * 10**9)).any(): raise ValueError('Bars not aligned to declared timeframe')
            cutoff = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz='UTC')
            cutoff = cutoff.tz_localize('UTC') if cutoff.tzinfo is None else cutoff.tz_convert('UTC')
            if (frame.timestamp + pd.Timedelta(minutes=minutes) > cutoff).any(): raise ValueError('Dataset contains unclosed or future bars')
            deltas = frame.timestamp.diff().dropna().dt.total_seconds()
            if (deltas < minutes * 60).any(): raise ValueError('Bars overlap at declared timeframe')
            row.update(audit, status='DATASET_AVAILABLE', error=None)
        except (ValueError, OSError, KeyError, pd.errors.ParserError) as exc:
            row['error'] = str(exc)
            if path.exists():
                row['sha256'] = file_sha256(path)
                try:
                    f = pd.read_csv(path); t = pd.to_datetime(f.get('datetime', f.get('timestamp')), utc=True, errors='coerce')
                    row.update(rows=len(f), columns=list(f), NaN={str(k): int(v) for k,v in f.isna().sum().items()},
                               duplicates=int(t.duplicated().sum()), chronological=bool(t.is_monotonic_increasing),
                               start=str(t.min()), end=str(t.max()))
                except (ValueError, AttributeError, TypeError): pass
        return row

    def scan(self, markets=MARKETS, timeframes=None, derive=True, as_of=None):
        timeframes = tuple(timeframes or TIMEFRAMES)
        files = list((self.root / 'data/cloud').glob('*.csv'))
        rows = []
        for market in markets:
            for tf in timeframes:
                if tf not in TIMEFRAMES: raise ValueError(f'Unsupported timeframe {tf}')
                matches = [p for p in files if p.stem.upper() in {f'{market}_{a}' for a in ALIASES[tf]}]
                if len(matches) == 1: row = self._audit(matches[0], market, tf, as_of=as_of)
                else:
                    row = {'market': market, 'timeframe': tf, 'status': 'DATASET_INVALID' if matches else 'DATASET_MISSING',
                           'path': None, 'kind': 'native', 'rows': None, 'start': None, 'end': None, 'sha256': None,
                           'columns': [], 'duplicates': None, 'NaN': None, 'chronological': None,
                           'error': 'Ambiguous native datasets' if matches else 'No native dataset', 'source_timeframe': None}
                rows.append(row)
        if derive:
            for row in sorted(rows, key=lambda r: TIMEFRAMES[r['timeframe']]):
                if row['status'] != 'DATASET_MISSING': continue
                sources = [r for r in rows if r['market'] == row['market'] and r['status'] == 'DATASET_AVAILABLE'
                           and TIMEFRAMES[r['timeframe']] < TIMEFRAMES[row['timeframe']]]
                if not sources: continue
                source = max(sources, key=lambda r: TIMEFRAMES[r['timeframe']])
                frame, _ = audit_dataset(self.root / source['path'])
                cutoff = as_of or pd.Timestamp.now(tz='UTC')
                derived = resample_closed(frame, source['timeframe'], row['timeframe'], cutoff)
                if derived.empty: continue
                provenance = {'source_path': source['path'], 'source_timeframe': source['timeframe'],
                              'source_sha256': source['sha256'], 'method': 'complete_utc_open_buckets_v1',
                              'available_through': str(derived.available_at.iloc[-1])}
                target = self.root / 'data/derived' / f"{row['market']}_{row['timeframe']}_{source['sha256'][:12]}_{len(derived)}.csv"
                target.parent.mkdir(parents=True, exist_ok=True)
                content = derived.to_csv(index=False)
                expected_sha = hashlib.sha256(content.encode()).hexdigest()
                if not target.exists():
                    temp = target.with_suffix('.tmp'); temp.write_text(content); temp.replace(target)
                row.update(self._audit(target, row['market'], row['timeframe'], 'derived', provenance, as_of=as_of))
                if row.get('sha256') != expected_sha:
                    row.update(status='DATASET_INVALID', error='Derived content does not match its source provenance')
        self.records = rows
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp'); temp.write_text(json.dumps({'schema_version': 1, 'datasets': rows}, indent=2)+'\n'); temp.replace(self.path)
        return rows

    def resolve(self, market, timeframe, verify=True):
        row = next((r for r in self.records if r['market'] == market and r['timeframe'] == timeframe), None)
        if row is None or row['status'] == 'DATASET_MISSING': raise FileNotFoundError(f'DATASET_MISSING: {market} {timeframe}')
        if row['status'] != 'DATASET_AVAILABLE': raise ValueError(f'DATASET_INVALID: {row.get("error")}')
        path = self.root / row['path']
        if verify:
            if not path.exists(): raise FileNotFoundError(f'DATASET_MISSING: {path}')
            if file_sha256(path) != row['sha256']: raise ValueError('DATASET_INVALID: SHA mismatch')
            audit_dataset(path)
            if row['kind'] == 'derived':
                prov = row['provenance']
                parent = self.resolve(market, prov['source_timeframe'], verify=True)
                if parent['sha256'] != prov['source_sha256']: raise ValueError('DATASET_INVALID: derived provenance mismatch')
        return row.copy()
