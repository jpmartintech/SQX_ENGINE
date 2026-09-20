from __future__ import annotations
import time, uuid
from .config import EngineConfig
from .data import load_ohlcv
from .features import prepare_features
from .generators import GeneticGenerator, RandomGenerator
from .backtest import FastEvaluator
from .funnel import QualityFunnel
from .store import StrategyStore
from .portfolio import PortfolioBuilder

class StrategyFactory:
    def __init__(self, config: EngineConfig): self.config=config
    def run(self):
        started=time.perf_counter(); run_id=str(uuid.uuid4()); data=load_ohlcv(self.config.get("data_path")); features=prepare_features(data); evaluator=FastEvaluator(data,features,self.config.get("backtest.initial_capital",10000),self.config.get("backtest.spread",0.0),self.config.get("backtest.slippage",0.0)); generator_cls=GeneticGenerator if self.config.get("generator.type","random")=="genetic" else RandomGenerator; gen=generator_cls(self.config.get("market","EURUSD"),self.config.get("timeframe","H1"),self.config.get("generator.seed",101),self.config.get("strategy.max_predicates",2)); funnel=QualityFunnel(self.config); store=StrategyStore(self.config.get("store.path","runs/sqx_engine.sqlite")); requested=int(self.config.get("generator.evaluations",100)); store.start_run((run_id,None,None,self.config.get("market"),self.config.get("timeframe"),self.config.get("generator.type","random"),self.config.get("generator.seed"),requested,0,0,0,0.0,self.config.config_hash,"RUNNING")); seen=set(); items=[]; rejected=0
        for _ in range(requested):
            s=gen.ask();
            if s.canonical_hash in seen: continue
            seen.add(s.canonical_hash); r=evaluator.evaluate(s); f=funnel.evaluate(s,r); store.add_strategy(s,r,f,self.config.get("generator.seed"),"CANDIDATE" if f["passed"] else "REJECTED"); rejected+=not f["passed"]
            if f["passed"]: items.append({"strategy":s,"result":r,"funnel":f})
            gen.tell(s, r)
        portfolio=PortfolioBuilder(self.config.get("portfolio.max_strategies",10),self.config.get("portfolio.max_correlation",.7)).build(items); elapsed=time.perf_counter()-started; store.finish_run(run_id,(None,len(seen),len(seen),len(items),elapsed,"COMPLETE")); result={"run_id":run_id,"market":self.config.get("market"),"timeframe":self.config.get("timeframe"),"requested":requested,"generated":gen.generated,"unique":len(seen),"backtested":len(seen),"basic_pass":len(items),"rejected":rejected,"candidates":len(items),"portfolio_eligible":len(items),"portfolio_selected":len(portfolio["strategies"]),"runtime":elapsed,"strategies_per_sec":len(seen)/elapsed,"database":{"runs":store.count("runs"),"strategies":store.count("strategies"),"funnel":store.count("funnel"),"candidates":len(items)},"portfolio":{"strategy_ids":[x["result"].strategy_id for x in portfolio["strategies"]],"weights":portfolio["weights"],"average_correlation":portfolio["average_correlation"],"max_correlation":portfolio["max_correlation"]},"top_candidates":store.top_strategies(self.config.get("market"),self.config.get("timeframe"),3)}; store.close(); return result
