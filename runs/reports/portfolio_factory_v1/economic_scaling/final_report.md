# SQX PORTFOLIO FACTORY V1.0 — ECONOMIC SCALING FIX — FINAL STATUS

Root cause: **UNIT_ERROR at the FTMO interface**. The legacy simulator received dimensionless normalized returns as account-currency PnL. The corrected path converts returns to explicit account USD before FTMO evaluation. The correction does not manufacture leverage or change strategy results.

Original net_return semantics: **net evaluator PnL / 10,000, dimensionless account return**.
Original risk_level semantics: **direct multiplier; 1.0 means 1× normalized stream, not 1% and not stop-risk**.

Economic model: `pnl_t = net_return_t × account_capital × (risk_target / 0.01)`.
Risk sizing definition: account-return allocation target relative to a documented 1% baseline; stop-risk sizing is unavailable from the replay contract.

Legacy reproduction: **PASS** (same historical 6,000 portfolio evaluations; original files preserved).
Net-return semantics: **PASS**.
Dimensional validation: **PASS**.
Economic golden: **PASS**.

Pilot universe: **8,438**, deterministic pool **200**.
Portfolios evaluated: **6,000 × 4 risk targets = 24,000 FTMO evaluations**.

| Risk | PASS | FAIL_DAILY | FAIL_TOTAL | TIMEOUT |
|---:|---:|---:|---:|---:|
| 0.25% | 0 | 0 | 0 | 6,000 |
| 0.50% | 0 | 0 | 0 | 6,000 |
| 0.75% | 0 | 0 | 0 | 6,000 |
| 1.00% | 0 | 0 | 0 | 6,000 |

Tests: **PASS** (economic tests plus existing suite).
FAST golden: **PASS**.
AUDIT: **PASS**.
Portfolio golden: **PASS**.
Economic golden: **PASS**.

MTM feasibility: **REQUIRES_REPLAY_EXTENSION**. Exact floating-PnL FTMO evaluation needs causal per-bar position state and monetary exposure, which the sparse realized-only replay stream does not contain.

## OBSERVED

- The old path used normalized returns where the FTMO API expected USD PnL.
- The corrected path produces dimensional account PnL and diagnostic fields for final return, daily loss, total drawdown and distance to target.
- All corrected pilot outcomes remain TIMEOUT because the same 200-strategy pilot produces extremely small normalized cumulative returns over the simulator's 30-day window. Median 1.00% target final returns are approximately 2.11e-7 (Random), 5.13e-7 (Greedy), and 2.21e-7 (Genetic).

## INFERRED

- The historical 0% FTMO rate was partly obscured by the unit mismatch, but it was not caused by a hidden profitable portfolio being suppressed by a single arbitrary dollar constant. After dimensional correction, the pilot still does not approach the 10% target.
- A meaningful stop-risk calibration requires replay extensions carrying causal position size, stop distance and instrument monetary units.

## NOT ESTABLISHED

- Future FTMO performance, independent validation, optimal risk target, or suitability of any portfolio.
- A stop-loss risk interpretation for the 0.25–1.00% targets.

No Strategy Factory code, gates, Library contents, historical pilot outputs or existing tags were modified.
