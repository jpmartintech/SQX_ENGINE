from __future__ import annotations
from pathlib import Path
import json, sqlite3, datetime

class StrategyStore:
    def __init__(self, path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.db=sqlite3.connect(self.path); self.db.row_factory=sqlite3.Row; self._init()
    def _init(self):
        self.db.executescript("""CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, market TEXT, timeframe TEXT, generator TEXT, seed INTEGER, requested INTEGER, generated INTEGER, evaluated INTEGER, survived INTEGER, runtime REAL, config_hash TEXT, status TEXT); CREATE TABLE IF NOT EXISTS strategies(strategy_id TEXT PRIMARY KEY, canonical_hash TEXT UNIQUE, market TEXT, timeframe TEXT, direction TEXT, strategy_json TEXT, generation INTEGER, seed INTEGER, trade_count INTEGER, profit_factor REAL, expectancy REAL, expectancy_r REAL, sharpe REAL, max_drawdown REAL, win_rate REAL, stability_score REAL, plateau_score REAL, cost_score REAL, execution_score REAL, monte_carlo_score REAL, fitness REAL, status TEXT, created_at TEXT); CREATE TABLE IF NOT EXISTS funnel(strategy_id TEXT, run_id TEXT, stage TEXT, passed INTEGER, score REAL, reason TEXT, runtime REAL);"""); self.db.commit()
    def start_run(self, run): self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(run)); self.db.commit()
    def finish_run(self, run_id, values): self.db.execute("UPDATE runs SET finished_at=?,generated=?,evaluated=?,survived=?,runtime=?,status=? WHERE run_id=?",(*values,run_id)); self.db.commit()
    def add_strategy(self, s, r, f, seed, status):
        now=datetime.datetime.now(datetime.timezone.utc).isoformat(); self.db.execute("INSERT OR IGNORE INTO strategies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(r.strategy_id,r.canonical_hash,s.market,s.timeframe,s.direction,s.to_json(),0,seed,r.trade_count,r.profit_factor,r.expectancy,r.expectancy_r,r.sharpe,r.max_drawdown,r.win_rate,f["stability_score"],f["plateau_score"],f["cost_score"],f["execution_score"],f["monte_carlo_score"],r.expectancy_r,status,now));
        for stage, passed in f["stages"].items(): self.db.execute("INSERT INTO funnel VALUES (?,?,?,?,?,?,?)",(r.strategy_id,"",stage,int(passed),float(passed),None,0.0))
        self.db.commit()
    def top_strategies(self, market=None, timeframe=None, limit=50):
        q="SELECT * FROM strategies WHERE 1=1"; args=[]
        if market: q+=" AND market=?"; args.append(market)
        if timeframe: q+=" AND timeframe=?"; args.append(timeframe)
        q+=" ORDER BY expectancy_r DESC LIMIT ?"; args.append(limit); return [dict(x) for x in self.db.execute(q,args)]
    def count(self, table): return int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    def close(self): self.db.close()

