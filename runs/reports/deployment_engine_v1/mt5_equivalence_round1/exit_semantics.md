# Exit semantics

Python `StrategyDefinition` has `target_atr=4.0` and `time_exit=24`. The frozen evaluator computes `target = entry + ATR(signal_bar) * target_atr` for LONG, checks STOP first, then TARGET, then TIME. Time is measured in bars with `held = i - entry_i + 1`; a time exit at `held >= 24` uses the close of that bar.

The pre-fix MQL5 exporter passed `atr*target_atr/stop_atr*stop` as a distance, where `stop` was already `atr*stop_atr`, yielding `target_atr * ATR^2` rather than `target_atr * ATR`. This is the demonstrated root cause of the artificial near-entry TPs and extra MT5 trade.

Current MQL5 time-exit handling is documented as a follow-up runtime item: the individual pre-fix EA did not invoke the common position time-exit manager in `OnTick`. This equivalence round fixes the demonstrated TP translation first and records the remaining runtime requirement explicitly.
