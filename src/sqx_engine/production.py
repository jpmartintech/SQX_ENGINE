"""Sequential, resumable production orchestration; no trading-policy changes."""
from contextlib import closing, redirect_stdout
from dataclasses import dataclass, asdict
from pathlib import Path
import copy
import fcntl
import hashlib
import itertools
import json
import math
import signal
import sqlite3
import time

import yaml

from .config import EngineConfig
from .data.catalog import DataCatalog
from .engine import StrategyFactory, _rss_mb
from .library import StrategyLibrary, utcnow
from .validation import ValidationFactory, DEFAULT_GATES

VERSION = '1.8.0'


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp'); temp.write_text(json.dumps(value, indent=2, default=str)+'\n'); temp.replace(path)


def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'), default=str).encode()).hexdigest()


@dataclass
class ProductionJob:
    job_id: str
    batch_id: str
    market: str
    timeframe: str
    seed: int
    evaluations: int
    grammar: str
    dataset: dict
    config: dict
    directory: str
    status: str = 'PENDING'
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    attempts: int = 0
    generated: int = 0
    candidates: int = 0
    validation_pass: int = 0
    oos_pass: int = 0
    promoted: int = 0
    runtime: float = 0.


class ProductionFactory:
    def __init__(self, root, jobs_path='runs/production/jobs.sqlite', library_path='library/strategies.sqlite'):
        self.root = Path(root).resolve()
        self.jobs_path = self.root / jobs_path
        self.library_path = self.root / library_path
        self.jobs_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.jobs_path); self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL,
                         status TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        self.db.execute('CREATE TABLE IF NOT EXISTS batch_jobs(batch_id TEXT NOT NULL,job_id TEXT NOT NULL REFERENCES jobs(job_id),PRIMARY KEY(batch_id,job_id))')
        self.db.execute('INSERT OR IGNORE INTO batch_jobs SELECT batch_id,job_id FROM jobs')
        self.db.commit()
        self.catalog = DataCatalog(self.root)

    def load_batch(self, path):
        value = yaml.safe_load(Path(path).read_text())
        return json.loads(json.dumps(value, default=str))

    def batch_id(self, batch):
        return digest({k:v for k,v in batch.items() if k != 'resource_guards'})

    def plan(self, batch):
        base_path = self.root / batch['base_config']
        base = EngineConfig.from_yaml(base_path)
        jobs = []; batch_id = self.batch_id(batch)
        if batch.get('grammar_version','v1.7') != 'v1.7': raise ValueError('Production grammar is frozen at v1.7')
        evaluations = int(batch['evaluations_per_job'])
        if evaluations <= 0: raise ValueError('evaluations_per_job must be positive')
        for market, tf, seed in itertools.product(batch['markets'], batch['timeframes'], batch['seeds']):
            error = None; status = 'PENDING'; dataset = {'market':market,'timeframe':tf,'sha256':None}
            try: dataset = self.catalog.resolve(market, tf)
            except FileNotFoundError as exc: status,error = 'SKIPPED_DATA_MISSING',str(exc)
            except ValueError as exc: status,error = 'SKIPPED_DATA_INVALID',str(exc)
            profile = batch.get('execution_profiles',{}).get(f'{market}_{tf}')
            if status == 'PENDING':
                if profile is None or not {'spread','slippage'} <= profile.keys():
                    status,error = 'FAILED','EXPLICIT_EXECUTION_PROFILE_REQUIRED'
                elif any(not math.isfinite(float(profile[k])) or float(profile[k]) < 0 for k in ('spread','slippage')):
                    status,error = 'FAILED','INVALID_EXECUTION_PROFILE'
            cfg = copy.deepcopy(base.raw)
            cfg.update(market=market,timeframe=tf,engine='numba',factory_version=VERSION,execution_profile=profile)
            cfg['generator'].update(seed=int(seed),evaluations=evaluations)
            cfg['strategy']['grammar_version'] = 'v1.7'
            if profile:
                cfg['backtest'].update({k:profile[k] for k in ('spread','slippage','initial_capital') if k in profile})
            if batch.get('temporal_policy'): cfg['temporal_policy'] = batch['temporal_policy']
            if not cfg.get('data_split') and not cfg.get('temporal_policy'): raise ValueError('Explicit temporal policy required')
            cfg['execution']['workers'] = batch.get('workers',1)
            for stage in ('validation','oos'):
                if cfg.get(stage, DEFAULT_GATES) != DEFAULT_GATES: raise ValueError('Validation/OOS gates must remain frozen')
            # Identity includes effective trading config and dataset provenance,
            # but excludes relocatable output paths and per-attempt guard limits.
            recipe_config = {k:v for k,v in cfg.items() if k not in {'store','checkpoint','data_path'}}
            job_id = digest({'market':market,'timeframe':tf,'seed':int(seed),'evaluations':evaluations,
                             'grammar':'v1.7','dataset':dataset,'config':recipe_config})
            directory = self.root / batch.get('output_root','runs/production') / market / tf / f'seed_{seed}' / job_id[:16]
            cfg['data_path'] = str(self.root / dataset['path']) if dataset.get('path') else ''
            cfg['store'] = {'path':str(directory/'discovery.sqlite')}
            cfg['checkpoint'] = {'path':str(directory/'checkpoint.json')}
            jobs.append(ProductionJob(job_id,batch_id,market,tf,int(seed),evaluations,'v1.7',dataset,cfg,str(directory),status,error))
        if len({j.job_id for j in jobs}) != len(jobs): raise ValueError('Duplicate matrix dimensions')
        return jobs

    def _save(self, job):
        payload = json.dumps(asdict(job),sort_keys=True)
        with self.db:
            self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,payload=excluded.payload,updated_at=excluded.updated_at',
                            (job.job_id,job.batch_id,job.status,payload,utcnow()))
            self.db.execute('INSERT OR IGNORE INTO batch_jobs VALUES (?,?)',(job.batch_id,job.job_id))
        if Path(job.directory).exists(): atomic_json(Path(job.directory)/'job.json',asdict(job))

    def status(self, batch_id=None):
        sql = 'SELECT j.payload FROM jobs j' + (' JOIN batch_jobs b ON b.job_id=j.job_id WHERE b.batch_id=?' if batch_id else '')
        rows = self.db.execute(sql,(batch_id,) if batch_id else ()).fetchall()
        jobs = [json.loads(r[0]) for r in rows]
        counts = {}
        for j in jobs: counts[j['status']] = counts.get(j['status'],0)+1
        return {'jobs':jobs,'counts':counts,'total':len(jobs)}

    def _guard(self, limits, started):
        if limits.get('max_runtime') is not None and time.perf_counter()-started >= float(limits['max_runtime']): raise InterruptedError('MAX_RUNTIME')
        if limits.get('max_memory_gb') is not None and _rss_mb() >= float(limits['max_memory_gb'])*1024: raise InterruptedError('MAX_MEMORY')

    def _execute(self, job, batch, started):
        directory = Path(job.directory); directory.mkdir(parents=True,exist_ok=True)
        profile = job.config.get('execution_profile')
        if not profile or any(k not in profile or not math.isfinite(float(profile[k])) or float(profile[k]) < 0 for k in ('spread','slippage')):
            raise ValueError('EXPLICIT_EXECUTION_PROFILE_REQUIRED')
        actual = self.catalog.resolve(job.market,job.timeframe)
        if actual != job.dataset: raise ValueError('Frozen job dataset/provenance changed; refusing resume')
        config_path = directory/'discovery.yaml'
        cfg = EngineConfig(job.config, str(config_path))
        if config_path.exists() and EngineConfig.from_yaml(config_path).config_hash != cfg.config_hash: raise ValueError('Stored job config changed')
        if not config_path.exists(): config_path.write_text(yaml.safe_dump(job.config,sort_keys=False))
        atomic_json(directory/'dataset.json',job.dataset)
        checkpoint = Path(job.config['checkpoint']['path'])
        if Path(job.config['store']['path']).exists() and not checkpoint.exists():
            raise ValueError('Existing discovery DB without checkpoint; refusing silent restart')
        limits = batch.get('resource_guards',{})
        self._guard(limits,started)
        engine_limits = dict(limits)
        if limits.get('max_runtime') is not None:
            engine_limits['max_runtime'] = max(0., float(limits['max_runtime']) - (time.perf_counter()-started))
        with (directory/'production.log').open('a',buffering=1) as log, redirect_stdout(log):
            discovery = StrategyFactory(cfg).run(resume=checkpoint.exists(),resource_limits=engine_limits)
        job.generated = discovery.get('unique',0)
        if discovery.get('status') == 'INTERRUPTED': raise InterruptedError(discovery.get('reason','SIGINT'))
        if job.generated != job.evaluations: raise ValueError('Discovery did not reach requested evaluations')
        job.candidates = discovery['candidates']; self._save(job)
        atomic_json(directory/'discovery_summary.json',discovery)
        self._guard(limits,started)
        validation_path = directory/'validation.sqlite'
        summary = None
        if validation_path.exists():
            with sqlite3.connect(validation_path) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                row = db.execute('SELECT summary FROM validation_runs WHERE source_run_id=? ORDER BY rowid DESC LIMIT 1',(discovery['run_id'],)).fetchone() if 'validation_runs' in tables else None
                if row: summary = json.loads(row[0])
        val_cfg = {'source_database':job.config['store']['path'],'source_run':discovery['run_id'],'source_config':str(config_path),
                   'source_checkpoint':str(checkpoint),'data_path':job.config['data_path'],'expected_sha256':job.dataset['sha256'],
                   'data_split':job.config.get('data_split'),'test_type':'TRUE_OOS','candidate_status':'CANDIDATE',
                   'validation':DEFAULT_GATES.copy(),'oos':DEFAULT_GATES.copy(),'expected_candidates':job.candidates,
                   'portfolio':copy.deepcopy(job.config.get('portfolio',{})), 'cache_size':512,
                   'results_database':str(validation_path),'summary_path':str(directory/'validation_summary.json'),
                   'csv_path':str(directory/'final_candidates.csv')}
        if job.config.get('temporal_policy'): val_cfg['temporal_policy'] = job.config['temporal_policy']
        (directory/'validation.yaml').write_text(yaml.safe_dump(val_cfg,sort_keys=False))
        if summary is None:
            summary = ValidationFactory(EngineConfig(val_cfg,str(directory/'validation.yaml'))).run()
        else:
            # Recover committed validation after interruption during exports.
            from .validation import export_stored_results
            export_stored_results(validation_path,summary['validation_run_id'],directory/'validation_summary.json',directory/'final_candidates.csv')
        job.validation_pass = summary['validation']['passed']; job.oos_pass = summary['oos']['passed']; self._save(job)
        self._guard(limits,started)
        library = StrategyLibrary(self.library_path)
        try:
            promotion = library.promote(job.config['store']['path'],validation_path,summary['validation_run_id'],
                                        job_id=job.job_id,config_path=config_path,dataset_path=job.config['data_path'],
                                        promotion_level=batch.get('promotion_policy','OOS_PASS'))
        finally: library.close()
        job.promoted = promotion['eligible']
        atomic_json(directory/'promotion.json',promotion)

    def run(self, batch, resume=False):
        batch_id = self.batch_id(batch)
        if resume:
            jobs = [ProductionJob(**r) for r in self.status(batch_id)['jobs']]
            if not jobs: raise ValueError('No stored batch to resume')
        else:
            jobs = self.plan(batch)
            # Register the entire plan atomically. An interruption here must not
            # leave a partial matrix that resume could mistake for the full batch.
            with self.db:
                for i,job in enumerate(jobs):
                    old = self.db.execute('SELECT payload FROM jobs WHERE job_id=?',(job.job_id,)).fetchone()
                    if old: jobs[i] = ProductionJob(**json.loads(old[0]))
                    else:
                        self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                                        (job.job_id,job.batch_id,job.status,json.dumps(asdict(job),sort_keys=True),utcnow()))
                    self.db.execute('INSERT OR IGNORE INTO batch_jobs VALUES (?,?)',(batch_id,job.job_id))
        previous = signal.getsignal(signal.SIGINT)
        def interrupt(_signum,_frame): raise KeyboardInterrupt()
        signal.signal(signal.SIGINT,interrupt)
        try:
            for job in jobs:
                if job.status == 'COMPLETE' or job.status.startswith('SKIPPED_'): continue
                if job.status == 'FAILED' and not resume: continue
                directory = Path(job.directory); directory.mkdir(parents=True,exist_ok=True)
                with (directory/'.lock').open('a') as lock:
                    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError: continue  # another producer owns it
                    # Recheck after acquiring the lock: a peer may have completed it.
                    latest = self.db.execute('SELECT payload FROM jobs WHERE job_id=?',(job.job_id,)).fetchone()
                    if latest and json.loads(latest[0])['status'] == 'COMPLETE': continue
                    job.status='RUNNING'; job.error=None; job.started_at=utcnow(); job.attempts+=1; self._save(job)
                    started = time.perf_counter(); stop_batch=False
                    try:
                        self._execute(job,batch,started)
                        job.status='COMPLETE'; job.completed_at=utcnow()
                    except (KeyboardInterrupt,InterruptedError) as exc:
                        job.status='INTERRUPTED'; job.error=str(exc) or 'SIGINT'; stop_batch=True
                    except Exception as exc:
                        job.status='FAILED'; job.error=f'{type(exc).__name__}: {exc}'
                    finally:
                        job.runtime += time.perf_counter()-started; self._save(job)
                    if stop_batch: break
        finally: signal.signal(signal.SIGINT,previous)
        result = self.status(batch_id)
        atomic_json(self.root/batch.get('output_root','runs/production')/f'batch_{batch_id[:16]}.json',result)
        return result

    def close(self): self.db.close()
