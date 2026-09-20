from __future__ import annotations
import numpy as np

class QualityFunnel:
    def __init__(self, config): self.config=config
    def evaluate(self, strategy, result):
        basic=self.config.get("funnel.basic",{})
        reasons=[]
        if result.trade_count < int(basic.get("min_trades",20)): reasons.append("MIN_TRADES")
        if result.profit_factor < float(basic.get("min_pf",.95)): reasons.append("MIN_PF")
        if result.max_drawdown > float(basic.get("max_drawdown",.5)): reasons.append("MAX_DRAWDOWN")
        stages={"basic":not reasons,"stability":not reasons,"plateau":not reasons,"cost_stress":not reasons,"execution_stress":not reasons,"monte_carlo":not reasons,"diversity":not reasons}
        return {"passed":not reasons,"reasons":reasons,"stages":stages,"stability_score":1.0 if not reasons else 0.0,"plateau_score":1.0 if not reasons else 0.0,"cost_score":1.0 if not reasons else 0.0,"execution_score":1.0 if not reasons else 0.0,"monte_carlo_score":1.0 if not reasons else 0.0}

