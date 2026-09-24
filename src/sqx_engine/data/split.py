"""Chronological partitions: no sorting, deduplication or cross-period warmup."""
from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from .loader import validate_ohlcv


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def audit_dataset(path):
    frame = pd.read_csv(path)
    frame.columns = [str(c).lower() for c in frame.columns]
    frame = frame.rename(columns={'datetime': 'timestamp'})
    required = {'timestamp', 'open', 'high', 'low', 'close', 'volume'}
    if required - set(frame):
        raise ValueError(f'Missing OHLCV columns: {sorted(required - set(frame))}')
    frame['timestamp'] = pd.to_datetime(frame.timestamp, utc=True, errors='coerce')
    for col in required - {'timestamp'}:
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    audit = {'rows': len(frame), 'start': str(frame.timestamp.min()), 'end': str(frame.timestamp.max()),
             'sha256': file_sha256(path), 'chronological': bool(frame.timestamp.is_monotonic_increasing),
             'duplicates': int(frame.timestamp.duplicated().sum()), 'NaN': {k: int(v) for k, v in frame.isna().sum().items()},
             'columns': list(frame), 'anomalies': []}
    if any(audit['NaN'].values()): audit['anomalies'].append('NaN')
    if not np.isfinite(frame[list(required - {'timestamp'})].to_numpy()).all(): audit['anomalies'].append('NON_FINITE')
    if audit['duplicates']: audit['anomalies'].append('DUPLICATE_TIMESTAMPS')
    if not audit['chronological']: audit['anomalies'].append('UNORDERED_TIMESTAMPS')
    if audit['anomalies']:
        raise ValueError(f'Dataset audit failed: {audit}')
    validate_ohlcv(frame)
    if 'spread' not in frame: frame['spread'] = 0.0
    return frame, audit


@dataclass(frozen=True)
class TimeSplit:
    development: float = .70
    validation: float = .15
    oos: float = .15
    method: str = 'chronological'

    def __post_init__(self):
        fractions = np.array([self.development, self.validation, self.oos])
        if self.method != 'chronological' or not np.isfinite(fractions).all() or (fractions <= 0).any() or not np.isclose(fractions.sum(), 1, rtol=0, atol=1e-12):
            raise ValueError('Expected positive chronological fractions summing to one')

    def boundaries(self, n):
        a, b = int(n * self.development), int(n * self.development) + int(n * self.validation)
        if not 0 < a < b < n: raise ValueError('Each split must contain rows')
        return a, b

    def partition(self, frame):
        validate_ohlcv(frame)
        if frame.timestamp.isna().any(): raise ValueError('Invalid timestamp')
        a, b = self.boundaries(len(frame))
        result = DatasetSplit(*(part.copy().reset_index(drop=True) for part in (frame.iloc[:a], frame.iloc[a:b], frame.iloc[b:])))
        assert result.development_df.timestamp.max() < result.validation_df.timestamp.min()
        assert result.validation_df.timestamp.max() < result.oos_df.timestamp.min()
        assert sum(len(part) for part in (result.development_df, result.validation_df, result.oos_df)) == len(frame)
        return result


@dataclass(frozen=True)
class DatasetSplit:
    development_df: pd.DataFrame
    validation_df: pd.DataFrame
    oos_df: pd.DataFrame

    def manifest(self):
        return {name: {'start': str(frame.timestamp.iloc[0]), 'end': str(frame.timestamp.iloc[-1]), 'bars': len(frame)}
                for name, frame in [('development', self.development_df), ('validation', self.validation_df), ('oos', self.oos_df)]}


def discovery_data(config):
    """Return only Development to every discovery consumer (features, fitness, funnel)."""
    from .loader import load_ohlcv
    if not config.get('data_split') and not config.get('temporal_policy'):
        return load_ohlcv(config.resolve_path('data_path')), None
    frame, audit = audit_dataset(config.resolve_path('data_path'))
    split = partition_dataset(config, frame)
    provenance = discovery_manifest(config, audit, split)
    return split.development_df, provenance


def partition_dataset(config, frame):
    """Legacy chronological split or explicit UTC date ranges, without fitting."""
    policy = config.get('temporal_policy')
    if not policy or policy.get('mode') == 'chronological':
        return TimeSplit(**config.get('data_split', {'development': .7, 'validation': .15, 'oos': .15})).partition(frame)
    if policy.get('mode') != 'explicit_dates': raise ValueError('Unknown temporal policy')
    validate_ohlcv(frame)
    parts, previous_end = [], None
    for name in ('development', 'validation', 'oos'):
        spec = policy[name]
        start = pd.Timestamp(str(spec['start']))
        start = start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
        end_raw = str(spec['end'])
        if end_raw == 'latest':
            if name != 'oos': raise ValueError('latest only allowed for OOS end')
            end = frame.timestamp.max() + pd.Timedelta(nanoseconds=1)
        else:
            end = pd.Timestamp(end_raw)
            end = end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
            # Date-only ends are inclusive days; timestamp ends are exclusive.
            if len(end_raw) == 10: end += pd.Timedelta(days=1)
        if end <= start or (previous_end is not None and start < previous_end): raise ValueError('Invalid or overlapping date ranges')
        part = frame[(frame.timestamp >= start) & (frame.timestamp < end)].copy().reset_index(drop=True)
        if part.empty: raise ValueError(f'Empty temporal partition: {name}')
        parts.append(part); previous_end = end
    return DatasetSplit(*parts)


def discovery_manifest(config, audit, split):
    result = {'scope': 'DEVELOPMENT_ONLY', 'dataset_sha256': audit['sha256'],
              'splits': split.manifest(), 'config_hash': config.config_hash,
              'backtest': config.get('backtest', {}), 'data_split': config.get('data_split')}
    if config.get('temporal_policy'): result['temporal_policy'] = config.get('temporal_policy')
    return result
