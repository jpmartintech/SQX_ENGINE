"""Numeric kernels for the V1.4 evaluator.

The kernels deliberately mirror the V1.3 loop, including its conservative
intrabar priority and equity-curve update behavior. They contain no pandas or
Python objects.
"""
from __future__ import annotations

try:
    import numba
    import numpy as np
    NUMBA_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on minimal fallback installs
    NUMBA_AVAILABLE = False
    simulate_aggregate = None
    simulate_rich = None


if NUMBA_AVAILABLE:
    @numba.njit(cache=True)
    def simulate_aggregate(open_, high, low, close, atr, signal, start, end,
                           initial_capital, direction, stop_atr, target_atr,
                           time_exit, spread, slippage, cost_multiplier, entry_delay):
        balance = initial_capital
        peak = initial_capital
        maxdd = 0.0
        position = 0
        entry_i = -1
        entry_price = 0.0
        risk = 0.0
        trades = 0
        gross_profit = 0.0
        gross_loss = 0.0
        sum_pnl = 0.0
        sum_r = 0.0
        sum_r2 = 0.0
        wins = 0
        longs = 0
        shorts = 0
        last = max(start, end - 1)
        for i in range(start, last):
            equity_value = initial_capital
            if position == 0 and signal[i]:
                candidate_entry = i + 1 + entry_delay
                if candidate_entry >= end:
                    break
                entry_i = candidate_entry
                entry_price = open_[candidate_entry]
                risk = atr[i] * stop_atr
                if not np.isfinite(risk) or risk <= 0.0:
                    dd = peak - equity_value
                    if dd > maxdd:
                        maxdd = dd
                    continue
                position = direction
                dd = peak - equity_value
                if dd > maxdd:
                    maxdd = dd
                continue
            if position == 0:
                equity_value = balance
                if equity_value > peak:
                    peak = equity_value
                dd = peak - equity_value
                if dd > maxdd:
                    maxdd = dd
                continue
            held = i - entry_i + 1
            stop = entry_price - risk if position == 1 else entry_price + risk
            target = entry_price + risk * target_atr / stop_atr if position == 1 else entry_price - risk * target_atr / stop_atr
            exit_price = 0.0
            exited = False
            if position == 1 and low[i] <= stop:
                exit_price = stop; exited = True
            elif position == -1 and high[i] >= stop:
                exit_price = stop; exited = True
            elif position == 1 and high[i] >= target:
                exit_price = target; exited = True
            elif position == -1 and low[i] <= target:
                exit_price = target; exited = True
            elif held >= time_exit:
                exit_price = close[i]; exited = True
            if exited:
                gross = exit_price - entry_price if position == 1 else entry_price - exit_price
                pnl = gross - (spread + slippage) * cost_multiplier
                r_value = pnl / max(risk, 1e-12)
                balance += pnl
                trades += 1
                sum_pnl += pnl
                sum_r += r_value
                sum_r2 += r_value * r_value
                if pnl > 0.0:
                    gross_profit += pnl; wins += 1
                elif pnl < 0.0:
                    gross_loss += pnl
                if position == 1:
                    longs += 1
                else:
                    shorts += 1
                position = 0
            equity_value = balance
            if equity_value > peak:
                peak = equity_value
            dd = peak - equity_value
            if dd > maxdd:
                maxdd = dd
        if position != 0 and entry_i < end:
            final_price = close[end - 1]
            gross = final_price - entry_price if position == 1 else entry_price - final_price
            pnl = gross - (spread + slippage) * cost_multiplier
            r_value = pnl / max(risk, 1e-12)
            balance += pnl
            trades += 1
            sum_pnl += pnl
            sum_r += r_value
            sum_r2 += r_value * r_value
            if pnl > 0.0:
                gross_profit += pnl; wins += 1
            elif pnl < 0.0:
                gross_loss += pnl
            if position == 1:
                longs += 1
            else:
                shorts += 1
            if balance > peak:
                peak = balance
            dd = peak - balance
            if dd > maxdd:
                maxdd = dd
        return (trades, balance, gross_profit, gross_loss, sum_pnl,
                sum_r, sum_r2, wins, longs, shorts, maxdd)


    @numba.njit(cache=True)
    def simulate_rich(open_, high, low, close, atr, signal, start, end,
                      initial_capital, direction, stop_atr, target_atr,
                      time_exit, spread, slippage, cost_multiplier, entry_delay):
        n = max(0, end - start)
        entry_idx = np.full(n, -1, dtype=np.int64)
        exit_idx = np.full(n, -1, dtype=np.int64)
        directions = np.zeros(n, dtype=np.int8)
        pnls = np.zeros(n, dtype=np.float64)
        rs = np.zeros(n, dtype=np.float64)
        held_bars = np.zeros(n, dtype=np.int64)
        reasons = np.zeros(n, dtype=np.int8)  # 1 STOP, 2 TARGET, 3 TIME, 4 END
        equity = np.full(n, initial_capital, dtype=np.float64)
        balance = initial_capital
        position = 0
        entry_i = -1
        entry_price = 0.0
        risk = 0.0
        count = 0
        last = max(start, end - 1)
        for i in range(start, last):
            if position == 0 and signal[i]:
                candidate_entry = i + 1 + entry_delay
                if candidate_entry >= end:
                    break
                entry_i = candidate_entry
                entry_price = open_[candidate_entry]
                risk = atr[i] * stop_atr
                if not np.isfinite(risk) or risk <= 0.0:
                    continue
                position = direction
                continue
            if position == 0:
                equity[i - start] = balance
                continue
            held = i - entry_i + 1
            stop = entry_price - risk if position == 1 else entry_price + risk
            target = entry_price + risk * target_atr / stop_atr if position == 1 else entry_price - risk * target_atr / stop_atr
            exit_price = 0.0
            reason = 0
            if position == 1 and low[i] <= stop:
                exit_price = stop; reason = 1
            elif position == -1 and high[i] >= stop:
                exit_price = stop; reason = 1
            elif position == 1 and high[i] >= target:
                exit_price = target; reason = 2
            elif position == -1 and low[i] <= target:
                exit_price = target; reason = 2
            elif held >= time_exit:
                exit_price = close[i]; reason = 3
            if reason != 0:
                gross = exit_price - entry_price if position == 1 else entry_price - exit_price
                pnl = gross - (spread + slippage) * cost_multiplier
                slot = count
                entry_idx[slot] = entry_i; exit_idx[slot] = i
                directions[slot] = position; pnls[slot] = pnl
                rs[slot] = pnl / max(risk, 1e-12); held_bars[slot] = held; reasons[slot] = reason
                count += 1
                balance += pnl
                position = 0
            equity[i - start] = balance
        if position != 0 and entry_i < end:
            final_price = close[end - 1]
            gross = final_price - entry_price if position == 1 else entry_price - final_price
            pnl = gross - (spread + slippage) * cost_multiplier
            slot = count
            entry_idx[slot] = entry_i; exit_idx[slot] = end - 1
            directions[slot] = position; pnls[slot] = pnl
            rs[slot] = pnl / max(risk, 1e-12); held_bars[slot] = end - entry_i; reasons[slot] = 4
            count += 1
            balance += pnl
        if n:
            equity[n - 1] = balance
        return (count, balance, entry_idx[:count], exit_idx[:count],
                directions[:count], pnls[:count], rs[:count], held_bars[:count],
                reasons[:count], equity)
