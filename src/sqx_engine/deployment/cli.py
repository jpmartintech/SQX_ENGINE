from __future__ import annotations
import argparse, csv, json, sqlite3
from dataclasses import replace
from pathlib import Path
from ..strategy import StrategyDefinition
from .backend import MQL5Backend
from .compare import compare_mt5_log
from .models import PortfolioDefinition

def main(argv=None):
    p=argparse.ArgumentParser(prog="sqx deployment"); s=p.add_subparsers(dest="cmd",required=True)
    e=s.add_parser("export"); e.add_argument("--portfolio-id"); e.add_argument("--portfolio-db",default="data/prop_portfolio_library.sqlite"); e.add_argument("--strategy-db",default="library/strategies.sqlite"); e.add_argument("--output",default="deployments/mql5")
    c=s.add_parser("compare-mt5"); c.add_argument("log"); c.add_argument("expected_json")
    a=p.parse_args(argv)
    if a.cmd=="compare-mt5": print(json.dumps(compare_mt5_log(a.log,json.loads(Path(a.expected_json).read_text())),indent=2)); return
    pc=sqlite3.connect(a.portfolio_db); pc.row_factory=sqlite3.Row
    if a.portfolio_id: pid=a.portfolio_id
    else: pid=pc.execute("select portfolio_id from portfolios where status='READY_FOR_PAPER' order by portfolio_id limit 1").fetchone()[0]
    pc.close(); out=Path(a.output); (out/"Experts/SQX").mkdir(parents=True,exist_ok=True)
    portfolio=PortfolioDefinition.from_sqlite(a.portfolio_db,pid,a.strategy_db); backend=MQL5Backend()
    single=portfolio.strategies[0].strategy
    sp=out/"Experts/SQX"/f"SQX_{single.readable_id.replace('-', '_')}.mq5"; pp=out/"Experts/SQX"/f"SQX_{pid.replace('-', '_')}.mq5"
    backend.export_strategy(single,sp,portfolio_id=pid,include_dir=out/"Include/SQX"); backend.export_portfolio(portfolio,pp,include_dir=out/"Include/SQX")
    print(json.dumps({"portfolio_id":pid,"single_strategy":str(sp),"portfolio":str(pp),"strategies":len(portfolio.strategies)},indent=2))
