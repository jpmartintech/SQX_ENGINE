from __future__ import annotations

from pathlib import Path
import datetime
import json
import sqlite3


class StrategyStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs(
          run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, market TEXT,
          timeframe TEXT, generator TEXT, seed INTEGER, requested INTEGER,
          generated INTEGER, evaluated INTEGER, survived INTEGER, runtime REAL,
          config_hash TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS strategies(
          strategy_id TEXT PRIMARY KEY, canonical_hash TEXT UNIQUE, market TEXT,
          timeframe TEXT, direction TEXT, strategy_json TEXT, generation INTEGER,
          seed INTEGER, trade_count INTEGER, profit_factor REAL, expectancy REAL,
          expectancy_r REAL, sharpe REAL, max_drawdown REAL, win_rate REAL,
          stability_score REAL, plateau_score REAL, cost_score REAL,
          execution_score REAL, monte_carlo_score REAL, fitness REAL,
          quality_score REAL DEFAULT 0, behavioral_cluster TEXT DEFAULT '',
          rejection_stage TEXT DEFAULT '', rejection_reason TEXT DEFAULT '',
          status TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS funnel(
          strategy_id TEXT, run_id TEXT, stage TEXT, passed INTEGER, score REAL,
          reason TEXT, runtime REAL);
        """)
        # Clean migration for databases created by the P0 schema.
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(strategies)")}
        for name, definition in (("quality_score", "REAL DEFAULT 0"), ("behavioral_cluster", "TEXT DEFAULT ''"), ("rejection_stage", "TEXT DEFAULT ''"), ("rejection_reason", "TEXT DEFAULT ''")):
            if name not in columns:
                self.db.execute(f"ALTER TABLE strategies ADD COLUMN {name} {definition}")
        self.db.commit()

    def start_run(self, run):
        self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(run))
        self.db.commit()

    def finish_run(self, run_id, values):
        self.db.execute("UPDATE runs SET finished_at=?,generated=?,evaluated=?,survived=?,runtime=?,status=? WHERE run_id=?", (*values, run_id))
        self.db.commit()

    def add_strategy(self, strategy, result, funnel, seed, status, run_id=""):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        reasons = ";".join(funnel.get("reasons", []))
        stages = funnel.get("stages", {})
        failed = next((k for k, v in stages.items() if not v), "" if funnel.get("passed") else "basic")
        values = (result.strategy_id, result.canonical_hash, strategy.market, strategy.timeframe, strategy.direction, strategy.to_json(), 0, seed, result.trade_count, result.profit_factor, result.expectancy, result.expectancy_r, result.sharpe, result.max_drawdown, result.win_rate, funnel.get("stability_score", 0), funnel.get("plateau_score", 0), funnel.get("cost_score", 0), funnel.get("execution_score", 0), funnel.get("monte_carlo_score", 0), result.expectancy_r, funnel.get("quality_score", 0), "", failed, reasons, status, now)
        self.db.execute("""INSERT OR REPLACE INTO strategies
          (strategy_id,canonical_hash,market,timeframe,direction,strategy_json,generation,seed,
           trade_count,profit_factor,expectancy,expectancy_r,sharpe,max_drawdown,win_rate,
           stability_score,plateau_score,cost_score,execution_score,monte_carlo_score,fitness,
           quality_score,behavioral_cluster,rejection_stage,rejection_reason,status,created_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
        for stage, passed in stages.items():
            self.db.execute("INSERT INTO funnel VALUES (?,?,?,?,?,?,?)", (result.strategy_id, run_id, stage, int(bool(passed)), float(funnel.get(f"{stage}_score", 1.0 if passed else 0.0)), None if passed else reasons, 0.0))

    def commit(self):
        self.db.commit()

    def top_strategies(self, market=None, timeframe=None, limit=50):
        q = "SELECT * FROM strategies WHERE 1=1"; args = []
        if market: q += " AND market=?"; args.append(market)
        if timeframe: q += " AND timeframe=?"; args.append(timeframe)
        q += " ORDER BY quality_score DESC, expectancy_r DESC LIMIT ?"; args.append(limit)
        return [dict(x) for x in self.db.execute(q, args)]

    def get_strategy(self, strategy_id):
        row = self.db.execute("SELECT * FROM strategies WHERE strategy_id=?", (strategy_id,)).fetchone()
        return dict(row) if row else None

    def count(self, table):
        return int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def close(self):
        self.db.close()
