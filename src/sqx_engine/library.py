"""Persistent strategy library: exact identity once, all discovery evidence retained."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3

from .config import EngineConfig
from .data.split import file_sha256
from .grammar import family_key
from .strategy import StrategyDefinition

LEVELS = {'GENERATED': 0, 'DEVELOPMENT_PASS': 1, 'VALIDATION_PASS': 2, 'OOS_PASS': 3}


def utcnow(): return datetime.now(timezone.utc).isoformat()


def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


class StrategyLibrary:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path); self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS library_jobs(job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, provenance TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS strategies(
          canonical_hash TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, market TEXT NOT NULL, timeframe TEXT NOT NULL,
          factory_version TEXT NOT NULL, grammar_version TEXT NOT NULL, seed INTEGER NOT NULL,
          source_run_id TEXT NOT NULL, validation_run_id TEXT, job_id TEXT NOT NULL REFERENCES library_jobs(job_id),
          direction TEXT NOT NULL, logic TEXT NOT NULL, predicates TEXT NOT NULL, atr_period INTEGER NOT NULL,
          stop_atr REAL NOT NULL, target_atr REAL NOT NULL, time_exit INTEGER NOT NULL,
          family TEXT NOT NULL, predicate_count INTEGER NOT NULL,
          development_start TEXT NOT NULL, development_end TEXT NOT NULL, validation_start TEXT NOT NULL, validation_end TEXT NOT NULL,
          oos_start TEXT NOT NULL, oos_end TEXT NOT NULL, development_metrics TEXT NOT NULL, validation_metrics TEXT, oos_metrics TEXT,
          dataset_sha256 TEXT NOT NULL, strategy_json TEXT NOT NULL, promotion_level TEXT NOT NULL,
          created_at TEXT NOT NULL, last_seen TEXT NOT NULL, discovery_count INTEGER NOT NULL DEFAULT 1,
          artifact_references TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS observations(
          canonical_hash TEXT REFERENCES strategies(canonical_hash), job_id TEXT REFERENCES library_jobs(job_id),
          source_run_id TEXT NOT NULL, validation_run_id TEXT NOT NULL, promotion_level TEXT NOT NULL,
          evidence TEXT NOT NULL, created_at TEXT NOT NULL,
          PRIMARY KEY(canonical_hash,job_id,source_run_id,validation_run_id,promotion_level));
        CREATE INDEX IF NOT EXISTS library_filters ON strategies(market,timeframe,family,promotion_level);
        ''')
        self.db.commit()

    def promote(self, source_database, validation_database, validation_run_id, *, job_id, config_path,
                dataset_path, factory_version='1.8.0', kind='PRODUCTION', promotion_level='OOS_PASS'):
        """Import verified completed evidence. OOS_PASS is the production default.

        Lower levels are explicitly analytical and excluded from default queries.
        Replaying the same observation is idempotent, including discovery_count.
        """
        if promotion_level not in LEVELS: raise ValueError('Unknown promotion policy')
        if not job_id: raise ValueError('A provenance job_id is required')
        source_path, validation_path = Path(source_database), Path(validation_database)
        cfg = EngineConfig.from_yaml(config_path)
        with closing(readonly(source_path)) as source, closing(readonly(validation_path)) as validation:
            run_row = validation.execute('SELECT summary,source_run_id FROM validation_runs WHERE validation_run_id=?', (validation_run_id,)).fetchone()
            if run_row is None: raise ValueError('Missing validation provenance')
            summary = json.loads(run_row['summary']); source_id = run_row['source_run_id']
            run = source.execute('SELECT * FROM runs WHERE run_id=?', (source_id,)).fetchone()
            if run is None or run['status'] != 'COMPLETE': raise ValueError('Source run incomplete')
            if source.execute('SELECT count(*) FROM runs').fetchone()[0] != 1: raise ValueError('Ambiguous source ownership')
            if cfg.config_hash != run['config_hash']: raise ValueError('Source config hash mismatch')
            prov_row = source.execute('SELECT manifest FROM discovery_provenance WHERE run_id=?',(source_id,)).fetchone()
            if prov_row is None: raise ValueError('Missing clean discovery provenance')
            provenance = json.loads(prov_row[0]); sha = file_sha256(dataset_path)
            if provenance['scope'] != 'DEVELOPMENT_ONLY' or provenance['dataset_sha256'] != sha or summary['data_audit']['sha256'] != sha:
                raise ValueError('Dataset provenance mismatch')
            if provenance['splits'] != summary['splits'] or provenance['config_hash'] != cfg.config_hash:
                raise ValueError('Temporal/config provenance mismatch')
            from .validation import DEFAULT_GATES
            if promotion_level == 'OOS_PASS' and any((DEFAULT_GATES | summary['config'].get(stage, {})) != DEFAULT_GATES for stage in ('validation', 'oos')):
                raise ValueError('Production promotion requires frozen validation/OOS gates')
            if summary['data_exposure']['test_type'] != 'TRUE_OOS': raise ValueError('Production library requires TRUE_OOS provenance')
            source_sha = file_sha256(source_path)
            if summary['source']['sha256'] != source_sha: raise ValueError('Source database fingerprint mismatch')
            job_prov = {'source_database': str(source_path.resolve()), 'source_database_sha256': source_sha,
                        'validation_database': str(validation_path.resolve()), 'validation_run_id': validation_run_id,
                        'config_path': str(Path(config_path).resolve()), 'config_sha256': file_sha256(config_path),
                        'dataset_path': str(Path(dataset_path).resolve()), 'dataset_sha256': sha,
                        'factory_version': factory_version, 'grammar_version': cfg.get('strategy.grammar_version', 'legacy'),
                        'source_run_id': source_id, 'seed': run['seed'], 'splits': summary['splits']}
            table = {'OOS_PASS':'oos_results', 'VALIDATION_PASS':'validation_results'}.get(promotion_level)
            if table:
                ids = [r[0] for r in validation.execute(f'SELECT strategy_id FROM {table} WHERE validation_run_id=? AND passed=1',(validation_run_id,))]
            else:
                sql = 'SELECT strategy_id FROM strategies' + (" WHERE status='CANDIDATE'" if promotion_level=='DEVELOPMENT_PASS' else '')
                ids = [r[0] for r in source.execute(sql)]
            inserted = duplicates = observations = 0
            with self.db:
                previous = self.db.execute('SELECT provenance FROM library_jobs WHERE job_id=?',(job_id,)).fetchone()
                encoded = json.dumps(job_prov,sort_keys=True)
                if previous and previous[0] != encoded: raise ValueError('Job provenance is immutable')
                self.db.execute('INSERT OR IGNORE INTO library_jobs VALUES (?,?,?,?)',(job_id,kind,encoded,utcnow()))
                for sid in ids:
                    row = source.execute('SELECT * FROM strategies WHERE strategy_id=?',(sid,)).fetchone()
                    if row is None: raise ValueError('Orphan strategy')
                    strategy = StrategyDefinition.from_json(row['strategy_json'])
                    if strategy.canonical_hash != row['canonical_hash']: raise ValueError('Canonical identity mismatch')
                    if (strategy.market,strategy.timeframe,strategy.grammar_version) != (cfg.get('market'),cfg.get('timeframe'),cfg.get('strategy.grammar_version','legacy')):
                        raise ValueError('Strategy/config identity mismatch')
                    stages = {}
                    for stage in ('development','validation','oos'):
                        ev = validation.execute(f'SELECT * FROM {stage}_results WHERE validation_run_id=? AND strategy_id=?',(validation_run_id,sid)).fetchone()
                        if ev:
                            if ev['canonical_hash'] != strategy.canonical_hash or ev['strategy_json'] != strategy.to_json() or ev['source_run_id'] != source_id:
                                raise ValueError('Strategy evidence mismatch')
                            stages[stage] = dict(ev)
                    if LEVELS[promotion_level] >= 1 and row['status'] != 'CANDIDATE': raise ValueError('Development gate failed')
                    if LEVELS[promotion_level] >= 2 and not stages.get('validation',{}).get('passed'): raise ValueError('Validation gate failed')
                    if LEVELS[promotion_level] >= 3 and not stages.get('oos',{}).get('passed'): raise ValueError('OOS gate failed')
                    metrics = {stage: stages[stage]['metrics'] if stage in stages else None for stage in ('development','validation','oos')}
                    if metrics['development'] is None:
                        metrics['development'] = json.dumps({k:row[k] for k in ['trade_count','profit_factor','expectancy','expectancy_r','sharpe','max_drawdown','win_rate']})
                    now = utcnow(); h = strategy.canonical_hash
                    values = {'canonical_hash':h,'strategy_id':sid,'market':strategy.market,'timeframe':strategy.timeframe,
                              'factory_version':factory_version,'grammar_version':strategy.grammar_version,'seed':run['seed'],
                              'source_run_id':source_id,'validation_run_id':validation_run_id,'job_id':job_id,
                              'direction':strategy.direction,'logic':strategy.logic,'predicates':json.dumps([p.to_dict() for p in strategy.predicates]),
                              'atr_period':strategy.atr_period,'stop_atr':strategy.stop_atr,'target_atr':strategy.target_atr,'time_exit':strategy.time_exit,
                              'family':family_key(strategy),'predicate_count':len(strategy.predicates),
                              **{f'{stage}_{bound}':summary['splits'][stage][bound] for stage in ('development','validation','oos') for bound in ('start','end')},
                              **{f'{stage}_metrics':m for stage,m in metrics.items()},'dataset_sha256':sha,'strategy_json':strategy.to_json(),
                              'promotion_level':promotion_level,'created_at':now,'last_seen':now,'discovery_count':1,
                              'artifact_references':json.dumps({'source_database':str(source_path.resolve()),'validation_database':str(validation_path.resolve()),'validation_run_id':validation_run_id})}
                    existing = self.db.execute('SELECT promotion_level FROM strategies WHERE canonical_hash=?',(h,)).fetchone()
                    if existing:
                        duplicates += 1
                        if LEVELS[promotion_level] > LEVELS[existing[0]]:
                            update = {k:v for k,v in values.items() if k not in {'canonical_hash','created_at','discovery_count'}}
                            self.db.execute('UPDATE strategies SET '+','.join(f'{k}=?' for k in update)+' WHERE canonical_hash=?',(*update.values(),h))
                    else:
                        self.db.execute('INSERT INTO strategies ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',tuple(values.values())); inserted += 1
                    result = self.db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?)',
                                            (h,job_id,source_id,validation_run_id,promotion_level,json.dumps({'provenance':job_prov,'metrics':metrics}),now))
                    if result.rowcount:
                        observations += 1
                        if existing:
                            count = self.db.execute('SELECT count(DISTINCT source_run_id) FROM observations WHERE canonical_hash=?',(h,)).fetchone()[0]
                            self.db.execute('UPDATE strategies SET discovery_count=?,last_seen=? WHERE canonical_hash=?',(count,now,h))
            return {'eligible':len(ids),'inserted':inserted,'duplicates_rejected':duplicates,'new_observations':observations}

    def list(self, market=None, timeframe=None, family=None, include_analysis=False, limit=100):
        where, args = ([] if include_analysis else ["promotion_level='OOS_PASS'"]), []
        for key,value in [('market',market),('timeframe',timeframe),('family',family)]:
            if value is not None: where.append(f'{key}=?'); args.append(value)
        sql = 'SELECT * FROM strategies'+ (' WHERE '+' AND '.join(where) if where else '')+' ORDER BY canonical_hash LIMIT ?'
        return [dict(r) for r in self.db.execute(sql,(*args,int(limit)))]

    def stats(self, include_analysis=False):
        where = '' if include_analysis else " WHERE promotion_level='OOS_PASS'"
        return {'total':self.db.execute('SELECT count(*) FROM strategies'+where).fetchone()[0],
                **{f'by_{key}':{r[0]:r[1] for r in self.db.execute(f'SELECT {key},count(*) FROM strategies'+where+f' GROUP BY {key}')} for key in ('market','timeframe','family')}}

    def close(self): self.db.close()
