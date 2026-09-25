import numpy as np
from sqx_engine.portfolio_factory import PortfolioEngine,PortfolioConstraints,PortfolioRequest,portfolio_hash,FtmoSimulator,FtmoConfig
from sqx_engine.portfolio_factory.economic import EconomicConfig,AccountEquityEngine

def test_weights_and_metrics():
 r=np.array([[1,1,-1],[2,2,-1],[1,1,-1.]],float); meta={'index':{'a':0,'b':1,'c':2},'rows':{'a':{'market':'EURUSD','timeframe':'H1','cluster':'1'},'b':{'market':'EURUSD','timeframe':'H1','cluster':'2'},'c':{'market':'USDJPY','timeframe':'H1','cluster':'3'}}}; e=PortfolioEngine(r,meta); x=e.evaluate(['a','c']); assert x['trade_count']==1; assert portfolio_hash(PortfolioRequest(('a','c')))==portfolio_hash(PortfolioRequest(('c','a')))
def test_constraints_and_ftmo():
 r=np.ones((5,2)); meta={'index':{'a':0,'b':1},'rows':{'a':{'market':'XAUUSD','timeframe':'H4','cluster':'1'},'b':{'market':'XAUUSD','timeframe':'H4','cluster':'1'}}}; e=PortfolioEngine(r,meta); assert e.validate(['a','b'],PortfolioConstraints(max_strategies=3,max_per_cluster=1))[0] is False; assert FtmoSimulator(FtmoConfig(profit_target=0.00000001,minimum_trading_days=1,max_days=5)).run(np.ones(5))['status']=='PASS'

def test_golden_portfolio_artifact():
    import json
    from pathlib import Path
    p=Path('runs/reports/portfolio_factory_v1/golden_portfolio.json')
    d=json.loads(p.read_text())
    assert d['portfolio_hash']
    assert len(d['strategy_ids'])==10
    assert d['metrics']['strategy_ids']==d['strategy_ids']

def test_economic_units_and_account_scaling():
    e=AccountEquityEngine(EconomicConfig(initial_capital=100000,risk_target=.01))
    m=e.metrics(np.array([.01,-.005]))
    assert np.allclose(m['pnl'],[1000.,-500.])
    assert np.allclose(m['equity'],[101000.,100500.])
    assert np.allclose(AccountEquityEngine(EconomicConfig(initial_capital=50000)).pnl([.01]),[500.])

def test_risk_target_is_explicit_and_no_double_scaling():
    a=AccountEquityEngine(EconomicConfig(initial_capital=100000,risk_target=.005))
    assert np.allclose(a.pnl([.01,-.01]),[500.,-500.])
    assert a.config.risk_multiplier == .5

def test_economic_scaling_prefix_is_causal():
    a=AccountEquityEngine(EconomicConfig(initial_capital=100000,risk_target=.01))
    assert np.allclose(a.pnl([.01,-.02]),a.pnl([.01,-.02,.5])[:2])
