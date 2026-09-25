# SQX LIBRARY REPLAY + BEHAVIORAL AUDIT — FINAL STATUS

Library strategies: **12,289**
Replayable: **12,289**
Successfully replayed: **12,289**
Replay equivalence: **PASS**
Failed: **0**
Legacy unavailable: **0**

Canonical strategies: **12,289**
Structural components: **11,340**
Behavioral components @ |corr|≥0.80: **6,494**
Behavioral effective count: **descriptive per-group components/rank; not a single alpha count**

Median nearest-neighbour correlation: **0.5831**
|corr| >= 0.80 neighbour: see behavioral_correlation_summary.csv
|corr| >= 0.95 neighbour: see behavioral_correlation_summary.csv
Positive both OOS halves: **8,460**
Positive expectancy @1.25x costs: **98.09%**
Positive expectancy @1.50x costs: **95.87%**
Positive expectancy @2.00x costs: **91.07%**
XAUUSD H4 behavioral components: **1444**
XAUUSD H4 temporal stability: see temporal_stability.csv
XAUUSD H4 cost robustness: see cost_sensitivity.csv

## Executive findings

- **OBSERVED:** all 12,289 stored strategies replayed successfully and matched stored OOS metrics within explicit tolerances.
- **OBSERVED:** behavioral correlation was computed from timestamp-aligned sparse exit-return streams, separately by market/timeframe.
- **OBSERVED:** XAUUSD H4 has a large behavioral component structure despite its large library count; details are in the CSV.
- **NOT ESTABLISHED:** future edge, independent alpha, or causal explanation for XAUUSD H4 survival.

## Replay equivalence

Baseline replay used the frozen V1.8 FastEvaluator, dataset provenance, next-bar execution, stored market/timeframe profiles and OOS boundaries. The persisted trade ledger contains entry/exit timestamps, reconstructed entry/exit prices, gross PnL, execution cost and net PnL. No strategies were generated or promoted.

## Behavioral method

Each strategy is a node. Returns are aligned by timestamp at trade exit. Pearson correlation is computed within each market/timeframe; edges at absolute correlation ≥0.80 define descriptive components. Trade overlap reports exact entry and exit timestamp overlap separately.

## Temporal stability

{
  "positive_both": 8460,
  "positive_first_only": 1268,
  "positive_second_only": 2561
}

## Cost stress

{
  "1.25": 0.9808772072585239,
  "1.5": 0.958662218243958,
  "2.0": 0.9107331760110668
}

## XAUUSD H4

- Behavioral components at `|corr|≥0.80`: **1,444**
- Positive expectancy in first OOS half: **4,532 / 4,558**
- Positive expectancy in second OOS half: **4,481 / 4,558**
- Positive expectancy both halves: **4,455 / 4,558**
- Positive expectancy at 1.25x / 1.50x / 2.00x costs: **4,557 / 4,557 / 4,555**

The replay confirms the reported OOS behavior under the frozen profile. Half-OOS and cost results are descriptive only; no gate or Library content was changed.

## Portfolio Factory contract

See portfolio_factory_data_contract.md. It exposes timestamped sparse returns, trade ledger, baseline/cost metrics, temporal slices and cluster identifiers without rerunning Strategy Factory.

## Integrity

- Library unchanged: **PASS**
- Replay DB integrity: **PASS**
- No generation: **PASS**
- No promotion: **PASS**
- Audit-only: **PASS**
- Pytest: **91 passed**
- FAST golden: **PASS**
- AUDIT: **PASS**

## Conclusions

**OBSERVED:** replay equivalence and timestamp-aligned behavioral summaries are available. **INFERRED:** behavioral components are a more useful downstream redundancy view than canonical counts, but depend on the selected correlation threshold and return representation. **NOT ESTABLISHED:** independent alpha, future profitability, or portfolio suitability.
