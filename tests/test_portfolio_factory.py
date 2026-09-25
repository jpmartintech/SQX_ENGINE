import numpy as np
from sqx_engine.portfolio_factory import PortfolioEngine,PortfolioConstraints,PortfolioRequest,portfolio_hash,FtmoSimulator,FtmoConfig

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
