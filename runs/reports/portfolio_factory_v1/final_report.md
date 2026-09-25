# SQX PORTFOLIO FACTORY V1.0 — FINAL STATUS

Strategy Factory: **V1.8 FROZEN**
Strategy Library: **12,289**
Replay dataset: **12,289/12,289 PASS**

Candidate universe: **8,438** strategies (positive both OOS halves and positive expectancy at 1.5x costs)

Portfolio engine: **PASS**
Common clock: **realized exit-event UTC clock; realized-only**
Risk engine: **PASS**
FTMO simulator: **PASS — REALIZED_ONLY**
Portfolio Library: **PASS**
Checkpoint/resume: **PASS schema and checkpoint**

Random pilot: **2,000 evaluations**
Greedy pilot: **2,000 evaluations**
Genetic pilot: **2,000 evaluations**

Portfolio sizes tested: **10, 20, 30**
Weighting methods: **EQUAL_WEIGHT, EQUAL_RISK**
Risk levels: **0.25%, 0.50%, 0.75%, 1.00% configuration-ready; pilot baseline 1.00**

Portfolios evaluated: **6,000**
Unique portfolios: **4,006**
Golden portfolio: **PASS** — 750f8071709dcdc3468c45652280594f0eb7f4b727a2a15f10facf7327640fa6
Tests: **PASS (94 tests)**
Strategy Factory golden: **PASS**
Factory integrity: **PASS**

## Architecture

Portfolio Factory consumes immutable strategy IDs and replay return streams. It has no generation, mutation, crossover, promotion or Strategy Library write path.

## Temporal integrity

All results are labelled `RETROSPECTIVE_PORTFOLIO_RESEARCH`. The 2024–2026 period was already observed by Strategy Factory. An untouched future period, paper-forward period or new chronological holdout is required for independent validation.

## Candidate universe

The pilot universe requires replay equivalence, positive expectancy in both OOS halves and positive expectancy at 1.5x costs. A deterministic pool of one representative per behavioral cluster, capped at 200 strategies, was used for resource control. No excluded strategy was deleted.

## Mathematics and risk

Returns are aggregated as realized PnL on the union of realized exit timestamps in UTC. Equal-weight and equal-risk weights are implemented. Correlation, market/timeframe/cluster constraints and concentration controls are configurable. MTM/floating PnL is not invented.

## FTMO simulator

Supports target, daily loss, total loss, minimum trading days and timeout. V1.0 is explicitly `REALIZED_ONLY`; floating PnL is unavailable in the replay contract.

## Search comparison

{
  "random": {
    "evaluated": 2000,
    "best_objective": 1.349592895750189,
    "best_sharpe": 1.3495932715009313,
    "median_sharpe": 0.845582403116748,
    "median_dd": 4.0612333325257004e-07,
    "ftmo_pass_rate": 0.0
  },
  "greedy": {
    "evaluated": 2000,
    "best_objective": 1.081219946411837,
    "best_sharpe": 1.081220736796917,
    "median_sharpe": 0.9599579187678721,
    "median_dd": 4.582053571428563e-07,
    "ftmo_pass_rate": 0.0
  },
  "genetic": {
    "evaluated": 2000,
    "best_objective": 1.347182296896108,
    "best_sharpe": 1.3471829468404977,
    "median_sharpe": 0.8537364187528573,
    "median_dd": 4.161562500000062e-07,
    "ftmo_pass_rate": 0.0
  },
  "interpretation": "pilot diagnostics only; no definitive portfolio selected"
}

The pilot is diagnostic. No definitive portfolio was selected.

## Portfolio Library

Stored separately in `data/portfolio_library.sqlite`, with order-independent exact `portfolio_hash` deduplication.

## Integrity

- Strategy Factory V1.8 unchanged: **PASS**
- Strategy Library unchanged: **PASS**
- Replay source unchanged: **PASS**
- Existing tags unchanged: **PASS**
- Portfolio DB integrity: **PASS**
- Synthetic tests: **PASS**
- Pytest: **PASS**
- FAST golden: **PASS**
- AUDIT: **PASS**

## Conclusions

**OBSERVED:** the downstream engine builds, constrains, evaluates and persists portfolios from immutable replay data. **INFERRED:** search-method differences are pilot diagnostics under the stated pool, objective and budget. **NOT ESTABLISHED:** future portfolio performance, independent validation, optimal search method, or FTMO survival outside this retrospective realized-only simulation.
