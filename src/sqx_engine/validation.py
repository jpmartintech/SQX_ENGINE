"""Evaluate immutable existing candidates. No generator or optimization dependency."""
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid
import warnings
from copy import deepcopy

import numpy as np
import pandas as pd

from .backtest import FastEvaluator
from .backtest.numba_core import NUMBA_AVAILABLE
from .config import EngineConfig
from .data.split import TimeSplit, audit_dataset, file_sha256
from .features import prepare_features
from .strategy import StrategyDefinition
from .grammar import family_key

METRICS = ('trade_count', 'profit_factor', 'expectancy', 'expectancy_r', 'sharpe', 'max_drawdown', 'win_rate', 'net_profit', 'return_pct')
DEFAULT_GATES = dict(min_trades=20, min_profit_factor=1.0, min_expectancy=0.0, min_sharpe=0.0)


def json_safe(value):
    if isinstance(value, dict): return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return 'Infinity' if value == math.inf else '-Infinity' if value == -math.inf else None
    return value


def dumps(value):
    return json.dumps(json_safe(value), sort_keys=True, allow_nan=False)


def metrics(result):
    return {name: getattr(result, name) for name in METRICS}


def check_gates(result, stage, config):
    gates = DEFAULT_GATES | config
    reasons = []
    for field, key, reason in [('trade_count', 'min_trades', f'LOW_{stage}_TRADES'),
                               ('profit_factor', 'min_profit_factor', f'LOW_{stage}_PF'),
                               ('expectancy', 'min_expectancy', f'NEGATIVE_{stage}_EXPECTANCY'),
                               ('sharpe', 'min_sharpe', f'LOW_{stage}_SHARPE')]:
        value = getattr(result, field)
        if math.isnan(value) or value < gates[key]: reasons.append(reason)
    if any(not math.isfinite(getattr(result, k)) for k in METRICS if k != 'profit_factor') or result.profit_factor == -math.inf:
        reasons.append(f'INVALID_{stage}_METRICS')
    return not reasons, reasons


def degradation(development, later):
    out = {}
    for name in ('profit_factor', 'expectancy', 'sharpe'):
        a, b = getattr(development, name), getattr(later, name)
        valid = math.isfinite(a) and math.isfinite(b)
        out[name + '_ratio'] = b / a if valid and a != 0 and math.isfinite(b / a) else None
        out['delta_' + name] = b - a if valid and math.isfinite(b - a) else None
    return out


def evaluate_stage(evaluator, strategies, stage, gates):
    records = []
    for strategy in strategies:
        before = strategy.to_json(), strategy.canonical_hash
        result = evaluator.evaluate(strategy, rich=stage == 'OOS')
        if before != (strategy.to_json(), strategy.canonical_hash): raise RuntimeError('Strategy changed during evaluation')
        passed, reasons = check_gates(result, stage, gates)
        records.append({'strategy': strategy, 'result': result, 'passed': passed, 'reasons': reasons})
    return records


def stage_summary(records):
    distribution = {}
    for field in ('profit_factor', 'expectancy', 'sharpe'):
        values = [getattr(r['result'], field) for r in records]
        finite = [v for v in values if math.isfinite(v)]
        distribution[field] = dict(zip(('P25', 'P50', 'P75', 'P95'), np.percentile(finite, [25, 50, 75, 95]).tolist())) if finite else dict.fromkeys(('P25', 'P50', 'P75', 'P95'))
        distribution[field]['non_finite_count'] = len(values) - len(finite)
    passed = sum(r['passed'] for r in records)
    return {'tested': len(records), 'passed': passed, 'failed': len(records) - passed, 'pass_rate': passed / len(records) if records else 0.0,
            'rejection_reasons': dict(Counter(reason for r in records for reason in r['reasons'])), 'distribution': distribution}


def final_portfolio(items, oos_frame, initial_capital, max_strategies=10, max_correlation=.70, diversity_correlation=.85, max_entry_overlap=.80):
    """Correlate realized PnL on identical OOS timestamps, not trade ordinal numbers.

    Ranking is frozen Development expectancy_r then canonical_hash. Daily combined
    Sharpe uses realized equity and sqrt(252); returns are equal initial allocations.
    """
    if not 0 <= max_strategies <= 10 or not 0 <= max_correlation <= 1 or not 0 <= diversity_correlation <= 1 or not 0 <= max_entry_overlap <= 1:
        raise ValueError('Invalid portfolio limits')
    started = time.perf_counter()
    arrays, entries = {}, {}
    for item in items:
        r = item['result']; pnl = pd.Series(0.0, index=pd.DatetimeIndex(oos_frame.timestamp))
        for trade in r.trades: pnl.loc[pd.Timestamp(trade['exit_time'])] += trade['pnl']
        arrays[r.strategy_id] = pnl.to_numpy()
        entries[r.strategy_id] = {str(t['entry_time']) for t in r.trades}
    def corr(a, b):
        x, y = arrays[a['result'].strategy_id], arrays[b['result'].strategy_id]
        return abs(float(np.corrcoef(x, y)[0, 1])) if len(x) > 1 and x.std() and y.std() else 0.0
    ordered = sorted(items, key=lambda i: (-i['development'].expectancy_r, i['result'].canonical_hash))
    diverse = []
    for item in ordered:
        clone = False
        for old in diverse:
            c = corr(item, old)
            a, b = entries[item['result'].strategy_id], entries[old['result'].strategy_id]
            overlap = len(a & b) / max(1, min(len(a), len(b)))
            if c >= diversity_correlation or (c >= diversity_correlation * .6 and overlap >= max_entry_overlap): clone = True; break
        if not clone: diverse.append(item)
    diversity_time = time.perf_counter() - started
    started = time.perf_counter(); selected = []
    for item in diverse:
        if len(selected) >= max_strategies: break
        if all(corr(item, old) <= max_correlation for old in selected): selected.append(item)
    pairs = [corr(a, b) for i, a in enumerate(selected) for b in selected[i + 1:]]
    if selected:
        changes = np.mean([arrays[i['result'].strategy_id] for i in selected], axis=0) / initial_capital
        combined = np.r_[0., np.cumsum(changes)]
        daily = pd.Series(changes, index=pd.DatetimeIndex(oos_frame.timestamp)).resample('B').sum().to_numpy()
        sharpe = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() else 0.0
        total_return, dd = float(combined[-1]), float(np.max(np.maximum.accumulate(combined) - combined))
    else: total_return = dd = sharpe = 0.0
    return {'eligible': len(items), 'after_diversity': len(diverse), 'selected': len(selected),
            'strategy_ids': [i['result'].strategy_id for i in selected],
            'weights': {i['result'].strategy_id: 1 / len(selected) for i in selected},
            'average_correlation': float(np.mean(pairs)) if pairs else 0.0, 'max_correlation': max(pairs, default=0.0),
            'combined_return': total_return, 'combined_sharpe': sharpe, 'combined_max_drawdown': dd,
            'status': 'FINAL_PORTFOLIO_READY' if selected else 'FINAL_PORTFOLIO_EMPTY',
            'measurement_period': 'OOS', 'selection_basis': 'Development rank; OOS gates and timestamp-aligned diversity',
            'performance_is_post_selection': True,
            'diversity_time': diversity_time, 'portfolio_time': time.perf_counter() - started}


class ValidationStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE IF NOT EXISTS validation_runs (validation_run_id TEXT PRIMARY KEY, source_run_id TEXT NOT NULL, timestamp TEXT NOT NULL, summary TEXT NOT NULL)')
        for table in ('development_results', 'validation_results', 'oos_results', 'final_candidates'):
            self.db.execute(f'''CREATE TABLE IF NOT EXISTS {table} (
                validation_run_id TEXT REFERENCES validation_runs(validation_run_id), source_run_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL, canonical_hash TEXT NOT NULL, split TEXT NOT NULL,
                metrics TEXT NOT NULL, passed INTEGER NOT NULL, status TEXT NOT NULL, rejection_reason TEXT NOT NULL,
                timestamp TEXT NOT NULL, strategy_json TEXT NOT NULL, degradation TEXT NOT NULL,
                PRIMARY KEY(validation_run_id, strategy_id))''')
        self.db.commit()

    def save(self, run_id, source_id, summary, development, validation, oos):
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute('INSERT INTO validation_runs VALUES (?,?,?,?)', (run_id, source_id, timestamp, dumps(summary)))
            for stage, records in [('DEVELOPMENT', development), ('VALIDATION', validation), ('OOS', oos)]:
                for row in records:
                    r, s = row['result'], row['strategy']
                    status = stage + ('_PASS' if row['passed'] else '_FAIL') if stage != 'DEVELOPMENT' else 'BASELINE'
                    values = (run_id, source_id, r.strategy_id, r.canonical_hash, stage, dumps(metrics(r)), int(row['passed']), status, ';'.join(row['reasons']), timestamp, s.to_json(), dumps(row.get('degradation', {})))
                    self.db.execute(f'INSERT INTO {stage.lower()}_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', values)
                    if stage == 'OOS' and row['passed']:
                        self.db.execute('INSERT INTO final_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', values)

    def close(self): self.db.close()


def load_source(config, splits, audit):
    path = config.resolve_path('source_database')
    source_hash = file_sha256(path)
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity != 'ok': raise ValueError(f'Source integrity: {integrity}')
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        runs = [dict(r) for r in db.execute('SELECT * FROM runs')]
        # V1.5 schema has global strategies, not a run-scoped strategy key.
        if len(runs) != 1: raise ValueError('Source must contain exactly one run; strategy ownership is otherwise ambiguous')
        run = runs[0]
        if run['status'] != 'COMPLETE' or config.get('source_run') != run['run_id']: raise ValueError('Source run mismatch or incomplete')
        source_config = EngineConfig.from_yaml(config.resolve_path('source_config'))
        if config.get('source_engine_override') is not None:
            source_config.raw['engine'] = config.get('source_engine_override')
        if source_config.config_hash != run['config_hash']: raise ValueError('Source config hash mismatch')
        clean = False
        if 'discovery_provenance' in tables:
            row = db.execute('SELECT manifest FROM discovery_provenance WHERE run_id=?', (run['run_id'],)).fetchone()
            if row:
                provenance = json.loads(row[0])
                expected = {'scope': 'DEVELOPMENT_ONLY', 'dataset_sha256': audit['sha256'], 'splits': splits.manifest(),
                            'config_hash': source_config.config_hash, 'backtest': source_config.get('backtest', {}), 'data_split': config.get('data_split')}
                if provenance != expected: raise ValueError('Discovery provenance does not match dataset/splits/execution')
                clean = True
        if not clean and config.get('test_type') != 'RETROSPECTIVE_SPLIT_TEST':
            raise ValueError('Unverified exposure: explicitly choose RETROSPECTIVE_SPLIT_TEST')
        rows = [dict(r) for r in db.execute('SELECT * FROM strategies WHERE status=? ORDER BY canonical_hash', (config.get('candidate_status', 'CANDIDATE'),))]
        strategies = []
        for row in rows:
            s = replace(StrategyDefinition.from_json(row['strategy_json']), strategy_id=row['strategy_id'])
            if s.canonical_hash != row['canonical_hash']: raise ValueError('Canonical hash mismatch')
            strategies.append(s)
        total = db.execute('SELECT COUNT(*) FROM strategies').fetchone()[0]
        expected_count = config.get('expected_candidates')
        if expected_count is not None and len(rows) != expected_count: raise ValueError('Unexpected candidate count')
        checkpoint_path = config.resolve_path('source_checkpoint')
        portfolio_count = None
        if checkpoint_path:
            checkpoint = json.loads(checkpoint_path.read_text())
            if checkpoint['run_id'] != run['run_id'] or checkpoint['status'] != 'COMPLETE': raise ValueError('Checkpoint mismatch')
            portfolio_count = checkpoint['result']['portfolio_selected']
    return strategies, source_config, {'source_run_id': run['run_id'], 'strategies': total, 'candidates': len(rows), 'portfolio': portfolio_count,
                                       'integrity_check': integrity, 'tables': tables, 'sha256': source_hash, 'clean': clean}


def canonical_output_config(config):
    """Canonical output interface, with explicit migration of deprecated aliases."""
    raw = deepcopy(config.raw)
    for canonical, alias in [('summary_path', 'summary_json'), ('csv_path', 'final_candidates_csv')]:
        if alias in raw:
            if canonical in raw and config.resolve_path(canonical).resolve() != config.resolve_path(alias).resolve():
                raise ValueError(f'Conflicting output keys: {canonical} and {alias}; use {canonical} only')
            warnings.warn(f'{alias} is deprecated; use {canonical}', FutureWarning, stacklevel=2)
            raw[canonical] = raw.pop(alias)
        if not raw.get(canonical): raise ValueError(f'Missing output path: {canonical}')
    return EngineConfig(raw, config.source)


class ValidationFactory:
    def __init__(self, config): self.config = canonical_output_config(config)

    def run(self):
        started = time.perf_counter(); cfg = self.config
        source_path, output_path = cfg.resolve_path('source_database'), cfg.resolve_path('results_database')
        protected = {source_path.resolve(), cfg.resolve_path('data_path').resolve(), cfg.resolve_path('source_config').resolve()}
        if cfg.resolve_path('source_checkpoint'): protected.add(cfg.resolve_path('source_checkpoint').resolve())
        outputs = [output_path, cfg.resolve_path('summary_path'), cfg.resolve_path('csv_path')]
        if len({p.resolve() for p in outputs}) != len(outputs) or any(p.resolve() in protected for p in outputs):
            raise ValueError('Outputs must be distinct and cannot overwrite inputs')
        frame, audit = audit_dataset(cfg.resolve_path('data_path'))
        if cfg.get('expected_sha256') and audit['sha256'] != cfg.get('expected_sha256'): raise ValueError('Dataset SHA256 mismatch')
        splits = TimeSplit(**cfg.get('data_split', {})).partition(frame)
        strategies, source_config, source = load_source(cfg, splits, audit)
        if not NUMBA_AVAILABLE: raise RuntimeError('V1.6 requires Numba')
        timings = {'load_time': time.perf_counter() - started}
        grammar_version = source_config.get('strategy.grammar_version', 'legacy')
        if any(s.grammar_version != grammar_version for s in strategies):
            raise ValueError('Strategy grammar does not match source configuration')
        def evaluator(data):
            return FastEvaluator(data, prepare_features(data, grammar_version=grammar_version), source_config.get('backtest.initial_capital', 10000),
                                 source_config.get('backtest.spread', 0.0), source_config.get('backtest.slippage', 0.0),
                                 cache_size=int(cfg.get('cache_size', 512)), engine='numba')
        t = time.perf_counter()
        dev_eval = evaluator(splits.development_df)
        development = [{'strategy': s, 'result': dev_eval.evaluate(s, rich=False), 'passed': True, 'reasons': []} for s in strategies]
        dev = {r['result'].canonical_hash: r['result'] for r in development}
        del dev_eval
        timings['development_time'] = time.perf_counter() - t
        t = time.perf_counter()
        validation = evaluate_stage(evaluator(splits.validation_df), strategies, 'VALIDATION', cfg.get('validation', {}))
        timings['validation_time'] = time.perf_counter() - t
        t = time.perf_counter()
        survivors = [r['strategy'] for r in validation if r['passed']]
        oos = evaluate_stage(evaluator(splits.oos_df), survivors, 'OOS', cfg.get('oos', {})) if survivors else []
        timings['oos_time'] = time.perf_counter() - t
        for row in validation + oos:
            row['degradation'] = degradation(dev[row['result'].canonical_hash], row['result'])
        final = [r for r in oos if r['passed']]
        for row in final: row['development'] = dev[row['result'].canonical_hash]
        portfolio = final_portfolio(final, splits.oos_df, source_config.get('backtest.initial_capital', 10000),
                                    cfg.get('portfolio.max_strategies', 10), cfg.get('portfolio.max_correlation', .70),
                                    cfg.get('diversity.max_correlation', .85), cfg.get('diversity.max_entry_overlap', .80))
        timings.update({k: portfolio.pop(k) for k in ('diversity_time', 'portfolio_time')})
        deg = {}
        for name, rows in [('validation', validation), ('oos', oos)]:
            deg[name] = {}
            for metric in ('profit_factor', 'expectancy', 'sharpe'):
                ratios = [r['degradation'][metric + '_ratio'] for r in rows if r['degradation'][metric + '_ratio'] is not None]
                deltas = [r['degradation']['delta_' + metric] for r in rows if r['degradation']['delta_' + metric] is not None]
                deg[name][metric] = {'median_ratio': float(np.median(ratios)) if ratios else None, 'median_delta': float(np.median(deltas)) if deltas else None, 'valid_ratios': len(ratios)}
        family_telemetry = {}
        for row in development:
            family = family_key(row['strategy'])
            counts = family_telemetry.setdefault(family, {'development_candidates': 0, 'validation_pass': 0, 'oos_pass': 0})
            counts['development_candidates'] += 1
        for stage, rows in [('validation_pass', validation), ('oos_pass', oos)]:
            for row in rows:
                if row['passed']: family_telemetry[family_key(row['strategy'])][stage] += 1
        summary = {'family_telemetry': family_telemetry,'validation_run_id': str(uuid.uuid4()), 'data_audit': audit, 'source': source, 'splits': splits.manifest(),
                   'data_exposure': {'historical_250k_used_full_dataset': 'NO' if source['clean'] else 'YES',
                                     'true_unseen_oos_possible_for_historical_run': 'YES' if source['clean'] else 'NO',
                                     'test_type': 'TRUE_OOS' if source['clean'] else 'RETROSPECTIVE_SPLIT_TEST'},
                   'execution': {'engine': 'numba', 'backtest': source_config.get('backtest', {}), 'feature_warmup': 'independent per split', 'entry': 'next bar', 'degradation_baseline': 'recomputed Development'},
                   'config': cfg.raw, 'validation': stage_summary(validation), 'oos': stage_summary(oos), 'degradation': deg,
                   'final_candidates': len(final), 'portfolio': portfolio, 'timings': timings}
        val = {r['result'].canonical_hash: r['result'] for r in validation}
        columns = ['strategy_id', 'canonical_hash'] + [f'{stage}_{metric}' for stage in ('development', 'validation', 'oos') for metric in ('trade_count', 'pf', 'expectancy', 'sharpe', 'maxdd')] + ['validation_pass', 'oos_pass']
        csv_path = cfg.resolve_path('csv_path'); csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns); writer.writeheader()
            for row in final:
                r = row['result']; output = {'strategy_id': r.strategy_id, 'canonical_hash': r.canonical_hash, 'validation_pass': True, 'oos_pass': True}
                for stage, result in [('development', dev[r.canonical_hash]), ('validation', val[r.canonical_hash]), ('oos', r)]:
                    for label, attr in [('trade_count', 'trade_count'), ('pf', 'profit_factor'), ('expectancy', 'expectancy'), ('sharpe', 'sharpe'), ('maxdd', 'max_drawdown')]: output[f'{stage}_{label}'] = getattr(result, attr)
                writer.writerow(output)
        if file_sha256(source_path) != source['sha256']: raise RuntimeError('Source changed during validation')
        store = ValidationStore(output_path)
        try:
            timings['total_time'] = time.perf_counter() - started
            store.save(summary['validation_run_id'], source['source_run_id'], summary, development, validation, oos)
            timings['total_time'] = time.perf_counter() - started
            with store.db:
                store.db.execute('UPDATE validation_runs SET summary=? WHERE validation_run_id=?', (dumps(summary), summary['validation_run_id']))
        finally: store.close()
        summary_path = cfg.resolve_path('summary_path'); summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(json_safe(summary), indent=2, allow_nan=False) + '\n')
        return summary
