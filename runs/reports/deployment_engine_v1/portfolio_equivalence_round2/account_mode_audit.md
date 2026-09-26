# Account mode audit — Round 2B

The generated EA logs only the generic label
`NETTING_OR_HEDGING_ACCOUNT_MODE`; it does not log
`ACCOUNT_MARGIN_MODE`. Source inspection therefore cannot resolve the actual
tester account mode.

The prompt examples describe simultaneous independent EURUSD strategy
positions, which would be consistent with HEDGING. They are not a complete
ticket/deal export, so this remains `PARTIAL`, not a certified account-mode
result. Export the tester account mode or add one diagnostic
`AccountInfoInteger(ACCOUNT_MARGIN_MODE)` log line before the next run.
