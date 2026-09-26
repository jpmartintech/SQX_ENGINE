import csv, json
from pathlib import Path
from dataclasses import replace
from sqx_engine.strategy import Predicate, StrategyDefinition
from sqx_engine.deployment import MQL5Backend, PortfolioDefinition, UnsupportedPredicateError
from sqx_engine.deployment.backend import magic_number
from sqx_engine.deployment.compare import compare_mt5_log

def test_mapping_rejects_unknown_predicate(tmp_path):
    s=StrategyDefinition("EURUSD","H1","LONG",(Predicate("unknown.feature",">",0),))
    try: MQL5Backend().export_strategy(s,tmp_path/"x.mq5")
    except UnsupportedPredicateError as e: assert e.code=="EXPORT_REJECT_UNSUPPORTED_PREDICATE"
    else: assert False

def test_strategy_export_deterministic(tmp_path):
    s=StrategyDefinition("EURUSD","H1","LONG",(Predicate("rsi_14","<",40),),grammar_version="v1.7")
    a=tmp_path/"a.mq5"; b=tmp_path/"b.mq5"; MQL5Backend().export_strategy(s,a); MQL5Backend().export_strategy(s,b)
    assert a.read_text()==b.read_text() and "shift=1" in a.read_text()
    assert magic_number(s.canonical_hash)==magic_number(s.canonical_hash)

def test_ready_portfolio_loads_and_exports(tmp_path):
    p=PortfolioDefinition.from_sqlite("data/prop_portfolio_library.sqlite","SQX-PROP-02760ECAC8BA")
    out=tmp_path/"p.mq5"; MQL5Backend().export_portfolio(p,out)
    text=out.read_text(); assert len(p.strategies)==20; assert p.portfolio_id in text; assert text.count("static bool SQX_S")==20

def test_mt5_log_compare(tmp_path):
    p=tmp_path/"log.csv"; fields=["timestamp","portfolio_id","strategy_id","event","symbol","timeframe","direction","price","volume","stop","requested_risk","balance","equity","floating_pnl","open_risk","message"]
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerow({x:("2026" if x=="timestamp" else "S" if x=="strategy_id" else "1" if x=="direction" else "") for x in fields})
    assert compare_mt5_log(p,[{"timestamp":"2026","strategy_id":"S","direction":"1","price":"","stop":""}])["status"]=="PASS"
