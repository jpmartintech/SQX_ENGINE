# Ownership fix before/after

| Metric | Before | After |
|---|---:|---:|
| MT5 trades | 66 | 60 |
| MT5 deals | 132 | 120 |
| Python trades | 64 | 64 |
| H1-bar matched | 50 chronological | 47 causal-bar |
| Python-only | 14 | 17 |
| MT5-only | 16 | 13 |
| Ambiguous | unresolved chronology | 0 |
| Cross-strategy closes | 21 | 0 |
| Orphan TIME_EXIT logs | 191 | 0 |
| Maximum open risk | 0.7614% | 0.2169% |
| Net PnL | -856.43 USD | -614.00 USD |
| Maximum equity DD | 0.96% | 0.72% |

The trade-count and PnL changes are diagnostic execution consequences only; they are not strategy-performance validation. The ownership invariant is the production result of this retest.
