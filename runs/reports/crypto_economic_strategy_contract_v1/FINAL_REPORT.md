# SQX CRYPTO ECONOMIC STRATEGY CONTRACT V1 — FINAL STATUS

STARTING COMMIT: `1666956`  
PRE-OOS FREEZE COMMIT: `146b585`  
FINAL COMMIT: recorded in the final VCS handoff  

## Input

Candidate universe: 7,017 unique definitions  
Old Library: 63  
Strategy generation: none  
Portfolio optimization: none  
LOCKBOX accesses: 0

## Economic contract

Initial equity: 1.0 normalized  
Base strategy risk: 1% current equity  
Maximum standalone heat: 1% current equity  
Sizing: remaining heat after existing open risk; resize/skip deterministically  
Compounding: current-equity fixed fractional  
Costs: frozen evaluator net-R including spread/slippage  
Funding: unavailable/not fabricated  
Ruin: equity <= 0; new entries halt

Open risk cannot accumulate beyond the intended 1% heat cap, although realized loss can exceed it through honest R overshoot/gap/slippage effects.

## Old 63 under bounded economics

Previous old-semantics ruin: 63/63. Bounded ruin by period: {'DEV': 1, 'OOS': 0, 'VAL': 0}. Previous aggregate PF>1/expectancy>0/return>0: 37/40/37.

The bounded model removes the universal ruin caused by unbounded concurrent fixed-fractional entries, but it does not guarantee positive edge; exact DEV/VAL/OOS quality remains separately measured.

## Frozen GOOD STRATEGY contract

- Causal, reproducible PRICE_ONLY definition and replay equivalence.
- Valid costs and no DEV/VAL ruin under bounded heat.
- DEV: PF > 1, positive return, positive exact economic expectancy, at least 30 trades.
- VAL: PF > 1, positive return, positive exact economic expectancy, at least 10 trades.
- OOS is excluded from admission and was read only after the pre-OOS freeze.

## Pre-OOS Library V2 candidate

Candidates: 7017  
Hard-valid: 4373  
DEV-valid: 2744  
VAL-valid: 518  
Admitted: 374  
Assets: 9  
LONG/SHORT: 188/186

## One-shot burned OOS diagnostic

Admitted-vs-rejected exact OOS results:

[
  {
    "group": "ADMITTED",
    "count": 374,
    "oos_positive": 82,
    "oos_positive_rate": 0.2192513368983957,
    "median_oos_pf": 0.8974344822981377,
    "median_oos_expectancy": -0.0005459902647753,
    "median_oos_return": -0.0610375771467691,
    "ruin_rate": 0.0053475935828877
  },
  {
    "group": "REJECTED",
    "count": 6643,
    "oos_positive": 358,
    "oos_positive_rate": 0.053891314165286766,
    "median_oos_pf": 0.8429669862640918,
    "median_oos_expectancy": -0.0005251346476682,
    "median_oos_return": -0.5280617422310498,
    "ruin_rate": 0.10718049074213458
  }
]

Admitted OOS positive count: 82  
Rejected OOS positive count: 358

The admitted group has a materially better OOS return median and lower ruin rate than rejected candidates, but median OOS PF and expectancy remain below 1/zero. This is improvement in selection quality, not proof of persistent edge.

## Decision

`ECONOMIC_ACCOUNTING_FIXED_EDGE_STILL_NONPERSISTENT`

The candidate-to-Library boundary is now economically coherent and materially filters the population, but DEV+VAL qualification does not produce a predominantly positive OOS population. No Portfolio Factory, Risk Engine, Execution Engine, or LOCKBOX access occurred.
