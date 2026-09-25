# R-based economic risk model

For a valid trade, `1R` is the loss at the initial protective stop before costs. The downstream R model uses:

```text
economic_gross_pnl = gross_R × account_equity × risk_target
economic_cost      = cost_R × account_equity × risk_target
economic_net_pnl   = net_R × account_equity × risk_target
```

The reported matrix uses `FIXED_INITIAL_CAPITAL_RISK`: the account baseline is fixed at the configured initial capital. `CURRENT_EQUITY_RISK` is reserved for a later explicit experiment and was not mixed into these results. This is not a modification of Strategy Factory sizing.
