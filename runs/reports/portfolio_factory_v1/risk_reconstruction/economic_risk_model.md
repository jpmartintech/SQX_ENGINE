# R-based economic risk model

For a valid trade, `1R` is the loss at the initial protective stop before costs. The downstream R model uses:

```text
economic_gross_pnl = gross_R × account_equity × risk_target
economic_cost      = cost_R × account_equity × risk_target
economic_net_pnl   = net_R × account_equity × risk_target
```

Both `FIXED_INITIAL_CAPITAL_RISK` and `CURRENT_EQUITY_RISK` are supported conceptually; the reported matrix uses current account-equivalent scaling with the certified realized-only stream. This is not a modification of Strategy Factory sizing.
