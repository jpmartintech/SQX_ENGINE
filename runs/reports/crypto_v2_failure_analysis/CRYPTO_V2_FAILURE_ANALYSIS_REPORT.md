# SQX CRYPTO V2 FAILURE ANALYSIS — FINAL STATUS

STARTING COMMIT: `0609916`  
TERMINAL DIAGNOSIS: `CRYPTO_V2_FAILURE_MULTIFACTORIAL`

## Data status

DEV, VAL, and OOS were treated as `BURNED_RESEARCH`. LOCKBOX was treated as
`UNCONSUMED_PROTECTED`.

LOCKBOX access before: 0  
LOCKBOX access after: 0

## V2 failure reproduction

The stored OOS result was reproduced exactly from the frozen 20 strategy
records: return `-66.8%`, PF `0.522`, expectancy `-0.301R`, MaxDD `68.8%`, and
5/20 positive strategies.

The recorded “portfolio” return is the arithmetic mean of independent
standalone strategy returns. It is not a chronological concurrent portfolio
replay. This is an aggregation limitation and an important V3 correction
requirement, although it does not make the individual OOS strategy failure
positive.

## Temporal and selection evidence

The frozen 100-strategy VAL library was replayed over D1–D6, VAL, and OOS. The
full 10,936 DEV-eligible records were replayed on burned OOS diagnostically;
duplicate definitions were retained by asset/hash identity.

Selected strategies had median best-window net-R concentration of `66.3%` and
median top-two concentration of `90.0%`. Selected median OOS trades were only
`8.0`. VAL expectancy to OOS expectancy correlation was negative
(`Spearman -0.175`); VAL PF to OOS PF was `-0.604`.

DEV slope to VAL expectancy was `0.052`; DEV slope to OOS was `0.253`.
D6-to-VAL was `-0.156`; VAL-to-OOS was `-0.207`. These support temporal
instability and selection decay, but not a reliable slope predictor.

The selection intensity was 100/10,936 (`0.91%`), followed by 20/100. This is
consistent with strong VAL winner’s-curse/selection overfit.

Selected median trade counts were DEV `77.5`, VAL `15.5`, and OOS `8.0`.
Weak effective trade support is therefore a major contributor.

## Contributions and costs

The selected set contained 13 LONG and 7 SHORT strategies. Both directions
failed in OOS; LONG contributed the larger aggregate loss. Losses were broad
across assets, with DOGE and BNB particularly harmful. No asset supplied a
stable counterweight.

Gross OOS median expectancy was `-0.233R`; baseline-cost expectancy was
`-0.301R`. Costs materially worsened the result but did not create the failure
from an otherwise positive gross edge.

Losses were mixed rather than one isolated event, with large negative months
in October 2025, February 2026, and April 2026.

## Leakage and engine audit

No direct leakage was found. Research normalization used each dataset’s first
observed close only; no future/global statistic was used. LOCKBOX was never
accessed.

The stored result is exactly reproducible, but V2’s portfolio accounting was
not the required concurrent model with floating PnL and exposure accounting.
The correct classification is therefore `PORTFOLIO_AGGREGATION_NOT_TRUE_CONCURRENT_REPLAY`,
not a proven low-level evaluator defect.

## Root cause

Primary mechanism: a multifactorial combination of:

1. VAL extreme-order selection overfit;
2. temporal edge decay/instability between VAL and OOS;
3. insufficient effective OOS trade support;
4. non-concurrent aggregation of standalone returns.

Secondary contributors are cost sensitivity, asset/direction concentration,
and possible signal-frequency drift. Regime shift and beta dependence remain
unresolved hypotheses.

Not supported: LOCKBOX access, direct information leakage, or a demonstrated
low-level evaluator defect.

## V3 implications

All items below are `HYPOTHESIS_FROM_BURNED_DATA`, not validated rules:

- Replace extreme VAL ranking with a predeclared policy incorporating
  uncertainty, temporal stability, and effective trade support.
- Require true chronological concurrent portfolio replay before portfolio
  economics are interpreted.
- Preserve low-sample states and require stronger effective trade support.
- Measure pre-OOS edge decay and signal-frequency stability.
- Add asset and direction concentration diagnostics before portfolio
  construction.

No V3 was implemented. V2 LOCKBOX remains untouched.
