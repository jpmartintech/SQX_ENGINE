# `net_return` semantics

`net_return` is **PASS: dimensionless evaluator account return**. Replay writes `float(trade.pnl) / 10000`. The source is explicit in `scripts/analysis/library_replay.py`; the stored `net_pnl` remains the evaluator PnL and the stored return is its fraction of the evaluator initial capital.

The legacy FTMO path consumed this fraction as dollar PnL. That is a unit error in the FTMO interface, although it does not change a percentage threshold when the account capital is applied consistently. The corrected path converts the fraction to account-currency PnL before applying daily and total-loss rules.
