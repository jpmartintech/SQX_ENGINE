from __future__ import annotations
from dataclasses import dataclass
import numpy as np, pandas as pd

@dataclass
class EvaluationResult:
    strategy_id: str; canonical_hash: str; trade_count: int; net_profit: float; return_pct: float; profit_factor: float; expectancy: float; expectancy_r: float; sharpe: float; max_drawdown: float; win_rate: float; average_trade: float; long_trades: int; short_trades: int; trade_returns: list; equity_curve: list; trades: list; runtime_seconds: float=0.0

class FastEvaluator:
    def __init__(self, data, features, initial_capital=10000, spread=0.0, slippage=0.0):
        self.data=data.reset_index(drop=True); self.features=features; self.initial_capital=initial_capital; self.spread=spread; self.slippage=slippage
    def _signal(self, strategy):
        masks=[]
        for p in strategy.predicates:
            x=self.features[p.feature]
            if p.feature == "close": x=x / np.r_[x[0],x[:-1]]
            m=x > p.value if p.operator == ">" else x < p.value
            masks.append(np.asarray(m & np.isfinite(x)))
        s=masks[0].copy()
        for m in masks[1:]: s=s&m if strategy.logic=="AND" else s|m
        return s & np.isfinite(self.features["atr_14"])
    def evaluate(self, strategy):
        signal=self._signal(strategy); d=self.data; atr=self.features["atr_14"]; trades=[]; equity=np.full(len(d),self.initial_capital,float); balance=self.initial_capital; position=None; entry_i=None; entry_price=None; risk=None
        for i in range(len(d)-1):
            if position is None and signal[i]:
                entry_i=i+1; entry_price=float(d.open.iloc[entry_i]); risk=float(atr[i]*strategy.stop_atr); position=strategy.direction; continue
            if position is None: equity[i+1]=balance; continue
            held=i-entry_i+1; stop=entry_price-risk if position=="LONG" else entry_price+risk; target=entry_price+risk*strategy.target_atr/strategy.stop_atr if position=="LONG" else entry_price-risk*strategy.target_atr/strategy.stop_atr; exit_price=None; reason=None
            if position=="LONG" and d.low.iloc[i]<=stop: exit_price=stop; reason="STOP"
            elif position=="SHORT" and d.high.iloc[i]>=stop: exit_price=stop; reason="STOP"
            elif position=="LONG" and d.high.iloc[i]>=target: exit_price=target; reason="TARGET"
            elif position=="SHORT" and d.low.iloc[i]<=target: exit_price=target; reason="TARGET"
            elif held>=strategy.time_exit: exit_price=float(d.close.iloc[i]); reason="TIME"
            if exit_price is not None:
                gross=(exit_price-entry_price) if position=="LONG" else (entry_price-exit_price); cost=self.spread+self.slippage; pnl=gross-cost; trades.append({"entry_time":d.timestamp.iloc[entry_i],"exit_time":d.timestamp.iloc[i],"direction":position,"pnl":float(pnl),"r":float(pnl/max(risk,1e-12)),"bars_held":held,"reason":reason}); balance+=pnl; position=None
            equity[i+1]=balance
        if position is not None:
            pnl=((float(d.close.iloc[-1])-entry_price) if position=="LONG" else (entry_price-float(d.close.iloc[-1])))-self.spread-self.slippage; trades.append({"entry_time":d.timestamp.iloc[entry_i],"exit_time":d.timestamp.iloc[-1],"direction":position,"pnl":float(pnl),"r":float(pnl/max(risk,1e-12)),"bars_held":len(d)-entry_i,"reason":"END"}); balance+=pnl
        equity[-1]=balance; pn=np.array([t["pnl"] for t in trades],float); rs=np.array([t["r"] for t in trades],float); wins=pn[pn>0]; losses=pn[pn<0]; pf=float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else (float("inf") if len(wins) else 0.0); peaks=np.maximum.accumulate(equity); dd=peaks-equity; maxdd=float(dd.max()/self.initial_capital); sharpe=float(rs.mean()/rs.std()*np.sqrt(252)) if len(rs)>1 and rs.std()>0 else 0.0
        years=int((d.timestamp.iloc[-1].year-d.timestamp.iloc[0].year)+1); active=int(len({t["exit_time"].year for t in trades})) if trades else 0
        return EvaluationResult(strategy.readable_id,strategy.canonical_hash,len(trades),float(pn.sum()),float((balance/self.initial_capital)-1),pf,float(pn.mean()) if len(pn) else 0.0,float(rs.mean()) if len(rs) else 0.0,sharpe,maxdd,float((pn>0).mean()) if len(pn) else 0.0,float(pn.mean()) if len(pn) else 0.0,sum(t["direction"]=="LONG" for t in trades),sum(t["direction"]=="SHORT" for t in trades),pn.tolist(),equity.tolist(),trades)

