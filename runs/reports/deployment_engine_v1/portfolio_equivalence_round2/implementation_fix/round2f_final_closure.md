# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2F — FINAL CLOSURE

Implementation commit: `116801a5200da463806f7e221195c462f3cdd3e9`

The final real MT5 traces were generated after the compression-parser fix and
match the operator-provided SHA256 values. No trading logic was modified during
this final comparison.

## Evidence

- Predicate trace: 10,560 rows; SHA256 `1ad14e1a403e875e3e49711e48572020ce161712b066163bfcc08d4459a514ac`.
- Raw-signal trace: 238 rows; SHA256 `7ff220d26c8d210083e601bce16d7064f2bc3a6ba99701d811ba8f69b8df1b62`.
- 20 strategies represented in the complete predicate trace; sparse raw signals are present for 18 active strategies.
- No duplicate strategy/bar keys; timestamps parse and are monotonic per strategy.

## Predicate equivalence

The exact MT5 H1 feed was evaluated by frozen Python semantics and compared to
the post-fix MQL5 trace. There are 10,540 comparable strategy-bars and 32,147
comparable predicates: 32,147 boolean matches and zero mismatches (100%).

Before → after mismatch counts:

- Structure ordering: 66 → 0.
- EMA slope seed/warm-up: 16 → 0.
- Compression multiplier parsing/dependency: 115 → 0.
- Other: 0 → 0.

Numeric values differ only at floating-point scale: MAE `8.597813165167506e-12`,
maximum absolute delta `2.075932500011056e-09`; no threshold or boolean decision
differs.

## Raw signals

Python exact-MT5-feed signals: 238. MQL5 signals: 238. Exact event matches:
238. Python-only: 0. MQL5-only: 0. Match rate: 100%.

The positive control `SQX-EURUSD-H1-63696db839ee` at signal bar
`2024-01-02 04:00 UTC` remains equivalent on all four predicates and the raw
signal. Its original Python-feed difference remains correctly classified as
DATA_FEED, not an implementation mismatch.

## Round 2D unresolved cases

The three remaining cases are resolved as `EXECUTION_INTRABAR`. Each has the
same causal H1 bar, Python MT5-feed signal, and MQL5 signal; the MT5 entry
timestamp is inside the H1 entry bar. Unresolved: 3 → 0.

## Regression status

Position ownership, TIME_EXIT, risk sizing/BaseRisk/MaxOpenRisk, concurrent
signal handling, and diagnostic tracing remain PASS. The exact-ticket close fix
is preserved. No new MT5 run is required for this closure.

## Gates

All semantic gates pass. Numeric equivalence is PARTIAL only in the permitted
floating-point sense; boolean decisions and raw signals are exact.

`ROUND_2F_COMPLETE`

`READY_FOR_FULL_MT5_OOS`
