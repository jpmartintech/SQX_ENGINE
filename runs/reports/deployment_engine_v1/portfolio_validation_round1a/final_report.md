# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 1A — FINAL STATUS

## Root cause

The first real portfolio run crashed because the generated portfolio supplied
600 rates to every strategy. The first deterministic unsafe path was
`SQX-EURUSD-H1-63696db839ee` / `S1`, predicate
`trend.ema_slope.200.1 > 0`, calling `SQX_EMA` with shift 1. Its seed index
was `801` (and the slope's second call required `802`) while the available
buffer had size 600. The compressed common source location was
`sqx_indicators.mqh` line 3, `a[z].close`.

## Fix

The canonical exporter now calculates the causal rate count per strategy
(803 for S1 and 808 for S13), while the common MQL5 library bounds-checks all
indicator, breakout, fractal and market-structure accesses. Insufficient
history returns safe not-ready values and cannot create a signal. The
individual EA remains at its 600-bar baseline because its certified longest
lookback fits there.

## Preservation

Strategy Factory V1.8, Grammar V1.7, Strategy Library, Portfolio Library,
strategy identities, canonical hashes, portfolio membership and risk policy
were not modified. Signal shift remains 1 and no lookahead or synthetic value
was introduced. The individual January equivalence baseline remains the
certified 5-trade sequence `TIME, STOP, STOP, STOP, TARGET` as previously validated.

## Artifacts

- Individual EA: `deployments/mql5/Experts/SQX/SQX_SQX_EURUSD_H1_1320ad51f2e8.mq5`
- Portfolio EA: `deployments/mql5/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5`
- Windows package: `deployments/mql5/package/`
- Common source: `src/sqx_engine/deployment/templates.py`
- Exporter: `src/sqx_engine/deployment/backend.py`

READY_FOR_PAPER coverage remains 20/20. Real MetaEditor compilation and MT5
execution are not available in WSL and are required next.

## Validation

`pytest`: **112 passed, 9 warnings**.

Deterministic generation, identity preservation and 20-strategy coverage
passed. `MQL5_COMPILE` is intentionally not declared PASS because the real
MetaEditor compiler is unavailable in Linux/WSL.

## Status

`MQL5_COMPILE = NOT_EXECUTED`

Reason: MetaEditor compiler unavailable in Linux/WSL.
