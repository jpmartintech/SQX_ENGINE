# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2F — FINAL STATUS

The final compression-parser retest evidence was verified byte-for-byte and
was generated after implementation commit `116801a5200da463806f7e221195c462f3cdd3e9`:

- predicate trace SHA256: `1ad14e1a403e875e3e49711e48572020ce161712b066163bfcc08d4459a514ac`
- raw-signal trace SHA256: `7ff220d26c8d210083e601bce16d7064f2bc3a6ba99701d811ba8f69b8df1b62`

The final comparison contains 10,540 comparable strategy-bars and 32,147
comparable predicates. Boolean matches are 32,147/32,147; mismatches are zero.
The 197 pre-fix mismatches are fully eliminated: structure 66 → 0, EMA 16 → 0,
compression 115 → 0, other 0 → 0. Numeric differences remain at floating-point
scale only (MAE `8.597813165167506e-12`, maximum `2.075932500011056e-09`).

Python exact-MT5-feed raw signals and MQL5 raw signals are both 238, with 238
exact event matches, zero Python-only, and zero MQL5-only events.

The three Round 2D unresolved cases are classified as `EXECUTION_INTRABAR`:
each has the same causal H1 signal and the MT5 order is executed inside the
corresponding H1 entry bar. Unresolved 3 → 0.

The common predicate template reconstructs the decimal multiplier generically.
The corrected portfolio EA/package was compiled and executed in MT5. The
positive control, exact-ticket ownership, TIME_EXIT, risk, and concurrent
signal regressions remain PASS.

Tests: `123 passed, 9 warnings`.
Trading logic modified during final comparison: NO.
Python frozen semantics changed: NO.

Status: `ROUND_2F_COMPLETE`.
Next: `READY_FOR_FULL_MT5_OOS`.
