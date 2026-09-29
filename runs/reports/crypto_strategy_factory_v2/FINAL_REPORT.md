# SQX CRYPTO STRATEGY FACTORY V2 — FINAL STATUS

## Status

The frozen bounded economic contract was reused. The 374/82 burned baseline reproduced. DEV-window exact replay found only weakly separating persistence characteristics, and the small fresh exact manufacturing run produced no VAL-admitted Library V3 candidates. OOS remains burned research only; LOCKBOX access remained zero.

## Findings

- Candidate universe: 7,017; historical Library V2: 374; burned OOS survivors: 82; failures: 292.
- Survivor median DEV positive-window fraction: 0.667; failure: 0.667.
- Survivor median late-DEV expectancy: 0.00130616; failure: 0.000613241.
- Fresh exact manufacturing: 18 Random + 36 Genetic; VAL evaluated: 54; admitted: 0.
- The prior Factory optimized aggregate DEV/VAL economics without enough temporal persistence control; the simple frozen persistence rules did not produce evidence strong enough to claim a successful redesign.

## Decision

**PERSISTENCE_SIGNAL_WEAK**

This is a historical redesign result, not protected validation. The next product action is to expand the pre-OOS information set/strategy research design before another manufacturing campaign; do not open LOCKBOX automatically.

{
  "starting_commit": "bf2c9c1",
  "factory_spec_commit": "009db34",
  "pre_val_freeze_commit": "8cbb2b4",
  "lockbox_access_before": 0,
  "lockbox_access_after": 0,
  "candidate_universe": 7017,
  "library_v2": 374,
  "burned_oos_survivors": 82,
  "burned_oos_failures": 292,
  "survivor_feature_medians": {
    "positive_window_fraction": 0.6666666666666666,
    "worst_window_expectancy": -0.00173830327730605,
    "best_window_share": 0.4525187883159819,
    "late_expectancy": 0.0013061603664871
  },
  "failure_feature_medians": {
    "positive_window_fraction": 0.6666666666666666,
    "worst_window_expectancy": -0.00112146669880695,
    "best_window_share": 0.4750465938786257,
    "late_expectancy": 0.00061324063615265
  },
  "fresh_manufacturing": {
    "random_per_asset": 2,
    "genetic_per_asset": 4,
    "unique": 54,
    "val_evaluated": 54,
    "library_v3_admitted": 0
  },
  "best_burned_policy_diagnostic": {
    "policy": "ROBUST_COMBINED",
    "selected": 263,
    "oos_positive_rate": 0.2433460076045627,
    "median_oos_pf": 0.8994249540839933,
    "median_oos_expectancy": -0.0005228523773968,
    "median_oos_return": -0.0676369077007168,
    "oos_ruin_rate": 0.0076045627376425,
    "research_only": true
  },
  "decision": "PERSISTENCE_SIGNAL_WEAK",
  "oos_used_for_admission": false
}
