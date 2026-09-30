# SQX MULTI-COIN PORTFOLIO FACTORY V1 — FINAL STATUS

Starting commit: `7e5bc9e273a710229a402a6869ca65ee583df61d`
PRE-OOS freeze commit: `c68d270669573d1a1e479b154a83d43e1ff3aa24`
Primary assets: BTC, AVAX, ETH, LINK, SOL

## Search

Full frozen library: 92,109 instances. Search pool: 200 instances, 40 per asset, DEV+VAL-only deterministic top/middle LONG/SHORT tiers. Random: 50,000 unique. Greedy: 45 evaluations. Genetic: 100,000 unique.

## Engine

Exact chronological multi-asset shared-equity replay passed the 20 independent Python reference checks recorded in `PORTFOLIO_ENGINE_EQUIVALENCE.json`; 500 fast candidates were searched. Total intended heat is 1% shared across active weighted strategy instances. No OOS influenced the search.

## DEV+VAL

Frozen frontier records: 673. The search contained 78596 DEV+VAL-valid candidates. The final frontier is dominated by single-asset candidates: 41; multi-asset candidates: 632.

## Burned OOS diagnostic

Frozen frontier tested: 673. Positive: 131 (19.5%). Median return: -0.4318. Median PF: 0.2830. Median MaxDD: -0.7729. This is burned research only.

BTC-only frozen control: 44 portfolios, 63.6% positive, median return +1.11% from the prior burned BTC portfolio diagnostic. The multi-coin frontier did not improve this control: its positive rate and median return were materially worse.

## Limitations

The exact engine and heat accounting are implemented, but a complete event-aligned PnL correlation/drawdown matrix across the 92k universe was not used to select portfolios. This loop therefore does not support a claim that cross-asset diversification improved the frontier.

## Decision

**MULTICOIN_PORTFOLIO_FACTORY_WEAK**

The current construction overfits DEV+VAL and is not ready for Risk Engine. Do not open LOCKBOX. Next action: redesign the portfolio search/persistence layer using DEV+VAL event-aligned behavioral fingerprints, then rerun the portfolio factory before Risk Engine.
