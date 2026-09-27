# SQX PROP STRATEGY FACTORY V1 — Architecture

## Scope

PROP_V1 is an additive production line for FTMO 2-Step portfolio components. It does not replace or mutate the General Strategy Factory. Its output is evaluated as portfolio material, not as a collection of “hero” standalone systems.

```text
GENERAL / PROP generation
        -> causal evaluation
        -> short-horizon metrics
        -> novelty and cost gates
        -> bounded marginal portfolio utility
        -> PROP_READY economic handoff
        -> Portfolio Factory
        -> Exact Equity Replay / FTMO rules
        -> MQL5 / MT5 validation
```

The initial product objectives are +10% Challenge and +5% Verification, with <=5 trading days a preferred horizon rather than a rule. The evaluator remains authoritative; no strategy fitness shortcut can promote a candidate directly to deployment.

## Product lines

- `GENERAL`: existing frozen factory and lineage.
- `PROP_V1`: specialized short-horizon component generation.
- `FTMO_CHALLENGE` and `FTMO_VERIFICATION`: downstream portfolio objectives over the same initial PROP pool.
- `FTMO_FUNDED`: reserved for a future payout mode and out of scope.

## Data flow and isolation

Generation uses Development only. Calibration may set documented funnel parameters. Validation is opened only after candidate and risk configuration freeze. OOS remains isolated per campaign. No rolling window may cross a split boundary.

