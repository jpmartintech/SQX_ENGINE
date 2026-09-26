import csv, json
import re
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
    text=a.read_text()
    assert text==b.read_text() and "shift=1" in text
    assert "static bool SQX_S0_Signal" not in text
    assert re.search(r"bool SQX_S0_Signal\(const MqlRates &rates\[\]", text)
    assert "SQX_LoadRates(_Symbol,PERIOD_H1,rates,600)" in text
    assert "ACCOUNT_EQUITY()" not in text
    assert "AccountInfoDouble(ACCOUNT_EQUITY)" in text
    assert "SQX_ManagePosition(_Symbol,InpMagic,PERIOD_H1,48" in text
    assert "SQX_HasPosition(_Symbol,InpMagic)" in text
    assert "atr*4/2*stop" not in text
    assert "SQX_SendEntry(_Symbol,ORDER_TYPE_BUY,volume,stop,atr*2," in text
    assert magic_number(s.canonical_hash)==magic_number(s.canonical_hash)

def test_ready_portfolio_loads_and_exports(tmp_path):
    p=PortfolioDefinition.from_sqlite("data/prop_portfolio_library.sqlite","SQX-PROP-02760ECAC8BA")
    out=tmp_path/"p.mq5"; MQL5Backend().export_portfolio(p,out,include_dir=tmp_path/"Include/SQX")
    text=out.read_text(); assert len(p.strategies)==20; assert p.portfolio_id in text
    assert "static bool SQX_S" not in text
    assert text.count("bool SQX_S") == 20
    assert "ACCOUNT_EQUITY()" not in text
    assert "SQX_ManagePosition(_Symbol,SQX_S0_MAGIC,SQX_S0_TF,SQX_S0_TIME_EXIT" in text
    assert "!SQX_HasPosition(_Symbol,SQX_S0_MAGIC)" in text
    assert "SQX_S0_TARGET_ATR/SQX_S0_STOP_ATR*stop" not in text
    indicators=(tmp_path/"Include/SQX/sqx_indicators.mqh").read_text()
    assert "bool SQX_LoadRates(string sym,ENUM_TIMEFRAMES tf,MqlRates &a[],int n)" in indicators
    assert "ArraySetAsSeries(a,true)" in indicators and "CopyRates(sym,tf,0,n,a)" in indicators

def test_real_deployment_identity_is_preserved():
    p=PortfolioDefinition.from_sqlite("data/prop_portfolio_library.sqlite","SQX-PROP-02760ECAC8BA")
    first=p.strategies[0].strategy
    assert first.readable_id=="SQX-EURUSD-H1-1320ad51f2e8"
    assert first.canonical_hash=="1320ad51f2e8f9579ad8543f669926cd6fe2b79923be06d2b7b3d6dd9313e765"
    assert p.portfolio_id=="SQX-PROP-02760ECAC8BA" and len(p.strategies)==20

def test_mt5_log_compare(tmp_path):
    p=tmp_path/"log.csv"; fields=["timestamp","portfolio_id","strategy_id","event","symbol","timeframe","direction","price","volume","stop","requested_risk","balance","equity","floating_pnl","open_risk","message"]
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerow({x:("2026" if x=="timestamp" else "S" if x=="strategy_id" else "1" if x=="direction" else "") for x in fields})
    assert compare_mt5_log(p,[{"timestamp":"2026","strategy_id":"S","direction":"1","price":"","stop":""}])["status"]=="PASS"
