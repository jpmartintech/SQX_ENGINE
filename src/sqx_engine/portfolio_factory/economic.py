"""Explicit economic/account scaling for downstream portfolio analysis.

Replay ``net_return`` is a dimensionless return: evaluator net PnL divided by
its configured initial capital (10,000).  This module deliberately keeps that
unit separate from account dollars and from the portfolio risk allocation.
"""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class EconomicConfig:
    initial_capital: float = 100_000.0
    # The replay contract has no stop-risk/position-size information.  These
    # are account-return allocation targets, not stop-loss risk claims.
    baseline_target: float = 0.01
    risk_target: float = 0.01

    @property
    def risk_multiplier(self) -> float:
        if self.baseline_target <= 0 or self.risk_target < 0:
            raise ValueError("risk targets must be non-negative and baseline > 0")
        return self.risk_target / self.baseline_target

class AccountEquityEngine:
    """Convert dimensionless returns to account PnL and equity."""
    def __init__(self, config: EconomicConfig):
        if config.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        self.config = config

    def pnl(self, normalized_returns):
        return np.asarray(normalized_returns, dtype=float) * self.config.initial_capital * self.config.risk_multiplier

    def equity(self, normalized_returns):
        return self.config.initial_capital + np.cumsum(self.pnl(normalized_returns))

    def metrics(self, normalized_returns, timestamps=None):
        pnl = self.pnl(normalized_returns)
        eq = self.config.initial_capital + np.cumsum(pnl)
        peak = np.maximum.accumulate(np.r_[self.config.initial_capital, eq])
        dd = float(np.max((peak[1:] - eq) / self.config.initial_capital)) if len(eq) else 0.0
        daily = {}
        if timestamps is not None:
            for ts, value in zip(timestamps, pnl):
                day = str(ts)[:10]
                daily[day] = daily.get(day, 0.0) + float(value)
        return {
            "pnl": pnl, "equity": eq, "net_return": float(pnl.sum() / self.config.initial_capital),
            "max_drawdown": dd, "daily_pnl": daily,
            "initial_capital": self.config.initial_capital,
            "risk_target": self.config.risk_target,
            "risk_multiplier": self.config.risk_multiplier,
        }
