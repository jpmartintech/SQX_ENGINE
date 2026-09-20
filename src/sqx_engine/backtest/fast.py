from __future__ import annotations

from dataclasses import dataclass, field
import time
import numpy as np


@dataclass
class EvaluationResult:
    strategy_id: str
    canonical_hash: str
    trade_count: int
    net_profit: float
    return_pct: float
    profit_factor: float
    expectancy: float
    expectancy_r: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    average_trade: float
    long_trades: int
    short_trades: int
    trade_returns: list
    equity_curve: list
    trades: list
    runtime_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)


class FastEvaluator:
    """Array-based causal evaluator with dataset-level predicate caching."""

    def __init__(self, data, features, initial_capital=10000, spread=0.0, slippage=0.0):
        self.data = data.reset_index(drop=True)
        self.features = features
        self.initial_capital = float(initial_capital)
        self.spread = float(spread)
        self.slippage = float(slippage)
        self._predicate_cache = {}
        self._signal_cache = {}
        self._arrays = {k: self.data[k].to_numpy(float) for k in ("open", "high", "low", "close")}
        self._arrays["timestamp"] = self.data.timestamp.to_numpy()

    def _predicate(self, p):
        key = (p.feature, p.operator, float(p.value), len(self.data))
        if key in self._predicate_cache:
            return self._predicate_cache[key]
        x = np.asarray(self.features[p.feature], dtype=float)
        if p.feature == "close":
            x = x / np.r_[x[0], x[:-1]]
        valid = np.isfinite(x)
        mask = x > p.value if p.operator == ">" else x < p.value
        out = np.asarray(mask & valid, dtype=bool)
        self._predicate_cache[key] = out
        return out

    def _signal(self, strategy):
        key = strategy.canonical_hash
        if key in self._signal_cache:
            return self._signal_cache[key]
        masks = [self._predicate(p) for p in strategy.predicates]
        signal = masks[0].copy()
        for mask in masks[1:]:
            signal = signal & mask if strategy.logic == "AND" else signal | mask
        signal &= np.isfinite(np.asarray(self.features["atr_14"], dtype=float))
        self._signal_cache[key] = signal
        return signal

    def evaluate(self, strategy, *, start=0, end=None, cost_multiplier=1.0, entry_delay=0, rich=True):
        started = time.perf_counter()
        a = self._arrays
        end = len(a["close"]) if end is None else min(int(end), len(a["close"]))
        start = max(0, int(start))
        signal = self._signal(strategy)
        atr = np.asarray(self.features["atr_14"], dtype=float)
        trades, equity = [], np.full(max(0, end - start), self.initial_capital, dtype=float)
        balance, position, entry_i, entry_price, risk = self.initial_capital, None, None, None, None
        for i in range(start, max(start, end - 1)):
            if position is None and signal[i]:
                candidate_entry = i + 1 + int(entry_delay)
                if candidate_entry >= end:
                    break
                entry_i, entry_price = candidate_entry, float(a["open"][candidate_entry])
                risk = float(atr[i] * strategy.stop_atr)
                if not np.isfinite(risk) or risk <= 0:
                    continue
                position = strategy.direction
                continue
            if position is None:
                equity[i - start] = balance
                continue
            held = i - entry_i + 1
            stop = entry_price - risk if position == "LONG" else entry_price + risk
            target = entry_price + risk * strategy.target_atr / strategy.stop_atr if position == "LONG" else entry_price - risk * strategy.target_atr / strategy.stop_atr
            exit_price, reason = None, None
            if position == "LONG" and a["low"][i] <= stop: exit_price, reason = stop, "STOP"
            elif position == "SHORT" and a["high"][i] >= stop: exit_price, reason = stop, "STOP"
            elif position == "LONG" and a["high"][i] >= target: exit_price, reason = target, "TARGET"
            elif position == "SHORT" and a["low"][i] <= target: exit_price, reason = target, "TARGET"
            elif held >= strategy.time_exit: exit_price, reason = float(a["close"][i]), "TIME"
            if exit_price is not None:
                gross = exit_price - entry_price if position == "LONG" else entry_price - exit_price
                pnl = gross - (self.spread + self.slippage) * float(cost_multiplier)
                trades.append({"entry_time": a["timestamp"][entry_i], "exit_time": a["timestamp"][i], "direction": position, "pnl": float(pnl), "r": float(pnl / max(risk, 1e-12)), "bars_held": held, "reason": reason})
                balance += pnl
                position = None
            equity[i - start] = balance
        if position is not None and entry_i < end:
            pnl = ((float(a["close"][end - 1]) - entry_price) if position == "LONG" else (entry_price - float(a["close"][end - 1]))) - (self.spread + self.slippage) * float(cost_multiplier)
            trades.append({"entry_time": a["timestamp"][entry_i], "exit_time": a["timestamp"][end - 1], "direction": position, "pnl": float(pnl), "r": float(pnl / max(risk, 1e-12)), "bars_held": end - entry_i, "reason": "END"})
            balance += pnl
        if len(equity): equity[-1] = balance
        pn = np.asarray([t["pnl"] for t in trades], dtype=float)
        rs = np.asarray([t["r"] for t in trades], dtype=float)
        wins, losses = pn[pn > 0], pn[pn < 0]
        pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else (float("inf") if len(wins) else 0.0)
        peaks = np.maximum.accumulate(equity) if len(equity) else np.array([self.initial_capital])
        maxdd = float(np.max(peaks - equity) / self.initial_capital) if len(equity) else 0.0
        sharpe = float(rs.mean() / rs.std() * np.sqrt(252)) if len(rs) > 1 and rs.std() > 0 else 0.0
        return EvaluationResult(strategy.readable_id, strategy.canonical_hash, len(trades), float(pn.sum()), float(balance / self.initial_capital - 1), pf, float(pn.mean()) if len(pn) else 0.0, float(rs.mean()) if len(rs) else 0.0, sharpe, maxdd, float((pn > 0).mean()) if len(pn) else 0.0, float(pn.mean()) if len(pn) else 0.0, sum(t["direction"] == "LONG" for t in trades), sum(t["direction"] == "SHORT" for t in trades), pn.tolist() if rich else [], equity.tolist() if rich else [], trades if rich else [], time.perf_counter() - started)
