from dataclasses import dataclass
from typing import Any
from ..backtest import FastEvaluator
from ..strategy import StrategyDefinition

@dataclass(frozen=True)
class ReplayRequest:
    strategy_id: str
    canonical_hash: str
    start: int = 0
    end: int | None = None
    cost_multiplier: float = 1.0
    rich: bool = True

@dataclass(frozen=True)
class ReplayResult:
    request: ReplayRequest
    metrics: dict[str, Any]
    trades: list[dict]
    equity_curve: list[float]
    return_stream: list[float]

class LibraryReplayEngine:
    """Replay one immutable StrategyDefinition with frozen V1.8 evaluator semantics.

    This class has no generator, funnel, promotion, or Library-write path by design.
    Dataset partitioning and provenance resolution remain responsibilities of the
    audit orchestration layer.
    """
    def __init__(self, evaluator: FastEvaluator):
        self.evaluator = evaluator

    def replay(self, strategy: StrategyDefinition, request: ReplayRequest) -> ReplayResult:
        if strategy.canonical_hash != request.canonical_hash:
            raise ValueError('canonical hash does not match replay request')
        if strategy.readable_id != request.strategy_id:
            raise ValueError('strategy id does not match replay request')
        result = self.evaluator.evaluate(strategy, start=request.start, end=request.end,
                                         cost_multiplier=request.cost_multiplier, rich=request.rich)
        metrics = {k: getattr(result, k) for k in
                   ('trade_count','profit_factor','expectancy','sharpe','max_drawdown','net_profit','return_pct')}
        returns = list(result.trade_returns)
        return ReplayResult(request, metrics, list(result.trades), list(result.equity_curve), returns)
