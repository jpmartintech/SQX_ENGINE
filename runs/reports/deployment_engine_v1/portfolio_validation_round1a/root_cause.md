# Portfolio EA Validation Round 1A — Root Cause

## Observed failure

The real MT5 tester terminated at `2024-01-02 00:05:00` with:

`array out of range in sqx_indicators.mqh (3,72)`

The pre-fix portfolio generated one `MqlRates` buffer per strategy, but every
strategy requested exactly 600 bars. The common EMA implementation seeds its
calculation at `z = shift + 4 * period`.

## Exact first failing path

The first portfolio strategy whose evaluation can reach an unsafe long EMA is:

- strategy: `SQX-EURUSD-H1-63696db839ee`
- portfolio index: `S1`
- predicate: `trend.ema_slope.200.1 > 0`
- helper: `SQX_Feature` → `SQX_EMA`
- causal shift: `1`
- first EMA seed index: `1 + 4×200 = 801`
- second slope EMA seed index: `2 + 4×200 = 802`
- pre-fix buffer: indices `0..599` (600 elements)

The reported compressed source line was the `SQX_EMA` statement `a[z].close`.
The first invalid access is therefore `a[801]`; the slope's second call would
also require `a[802]`. The strategy appears before the other 200-period EMA
strategies in the deterministic portfolio evaluation order.

The next long-EMA case is `S13`,
`SQX-EURUSD-H1-a18d86c3075c`, `trend.ema_slope.200.6`, which requires index
807 and 808 bars. This confirms the issue was portfolio-specific, not a
single-strategy data-feed failure.

## Why the certified single EA survived

`SQX-EURUSD-H1-1320ad51f2e8` uses EMA period 50 as its longest EMA and its
existing 600-bar buffer is sufficient. It never reaches the 200-period seed
index. The single EA therefore did not exercise the unsafe branch.

## Generic fix

The exporter now computes a causal rate count per strategy, preserving the
600-bar baseline and raising it to 803/808 where required. The common MQL5
indicator library now guards every array access family with
`SQX_RatesReady(...)`. Short data returns `EMPTY_VALUE` for numeric helpers or
`false` for pivot helpers; predicates reject `EMPTY_VALUE` and signals reject
an unavailable ATR. No missing indicator value is replaced with zero.

The generated portfolio keeps its existing per-strategy position gate and
identity metadata. No StrategyDefinition, canonical hash, portfolio member,
risk policy, or causal shift was changed.
