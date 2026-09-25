# Economic unit forensics (AUDIT_ONLY)

| Field | Definition / formula | Input units | Output units | Source |
|---|---|---|---|---|
| `gross_pnl` | evaluator trade PnL before costs | quote-price/account-unit model | evaluator account currency | `src/sqx_engine/backtest/fast.py`, `FastEvaluator` |
| `execution_cost` | spread + slippage deducted once per trade | price units | evaluator account currency | frozen V1.8 execution profile |
| `net_pnl` | gross PnL minus execution cost | account currency | account currency | replay `trades.net_pnl` |
| `net_return` | `net_pnl / 10000` | account currency | dimensionless fraction | `scripts/analysis/library_replay.py` |
| portfolio return | weighted sum of aligned strategy `net_return` | dimensionless | dimensionless | `PortfolioEngine.evaluate` |
| legacy FTMO input | portfolio return passed as if dollars | dimensionless | incorrectly treated as USD | `scripts/portfolio_factory_pilot.py` |
| corrected account PnL | `net_return × initial_capital × risk_target / 0.01` | fraction, USD | USD | `AccountEquityEngine` |
| account equity | initial capital + cumulative economic PnL | USD | USD | `AccountEquityEngine` |
| drawdown | peak-to-equity / initial capital | USD | dimensionless fraction | economic engine |

The replay representation is an account-return fraction based on the frozen evaluator's 10,000 initial-capital convention. It is not a pip value, contract PnL, or stop-risk unit. No monetary position size is present in the replay contract.
