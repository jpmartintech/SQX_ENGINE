# Evaluator forensics

`FastEvaluator` starts with `initial_capital=10,000`, but the trade loop uses one price unit: entry is the next bar open; `risk = ATR(signal_bar) × strategy.stop_atr`; stop and target are price distances; gross PnL is signed price difference for one unit; execution cost is `spread + slippage` in price units; net PnL is gross minus cost. There is no lot, contract-size, point-value, dollar-risk or ATR position sizing.

The evaluator writes `return_pct = balance / initial_capital - 1`. Replay stores each trade return as `net_pnl / 10,000`. Thus the denominator is the evaluator account normalization, not a 1R risk budget.

The initial stop is explicit in every stored StrategyDefinition through positive `stop_atr`; it is derivable at each signal from the original OHLC/ATR series. Time exits and stop/target priority remain frozen evaluator semantics.
