# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2F — FINAL STATUS

The post-fix MT5 evidence was verified byte-for-byte:

- predicate trace SHA256: `3284b24f502aa99e002c7adc077c1975068d3409255398d96eccd38dd9254e96`
- raw-signal trace SHA256: `114f96e66d5075ebe363bcb234d40eb05319b601aa20b9a856b4f67ca8df57d2`

Structure and EMA fixes passed: previous structure mismatches 66 → 0 and
previous EMA mismatches 16 → 0. Compression remained at 115 mismatches. The
additional proven cause is feature parsing: `StringSplit` converts the frozen
feature suffix `.1.5` into `p[4]=1`, `p[5]=5`, while the MQL5 implementation
used only `p[4]` and therefore applied a Keltner multiplier of 1.0 instead of
1.5. This generated the observed compression and four raw-signal mismatches.

The common predicate template now reconstructs the decimal multiplier
generically. The individual and portfolio EAs/package were regenerated. The
new source has not yet been compiled or executed in MT5, so the current
post-fix evidence cannot be reused as final evidence for this additional fix.

Tests: `123 passed, 9 warnings`.
Trading logic semantics changed: NO. MQL5 implementation changed: YES.
Python frozen semantics changed: NO.

Status: BLOCKED pending one MetaEditor compile and the prescribed January
diagnostic retest.
