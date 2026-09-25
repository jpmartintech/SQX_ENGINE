# SQX PORTFOLIO FACTORY — STRATEGY ECONOMIC RECONSTRUCTION — FINAL STATUS

10K denominator semantics: **evaluator initial-capital normalization**, not a risk budget or notional. Replay stores `net_pnl / 10,000`.

Evaluator position sizing: **fixed one price unit**. No lot, contract-size, point-value, dollar-risk or ATR quantity sizing exists in the frozen evaluator.

Stop-loss semantics: **explicit and derivable**. `risk = ATR(signal_bar) × stop_atr`; the evaluator enters next-bar open and applies frozen stop/target/time-exit priority.

R derivability:

- Library: **12,289 / 12,289 (100%)** from positive explicit `stop_atr`.
- Candidate universe: **8,438 / 8,438 (100%)**, based on the certified universe and the same StrategyDefinition property.
- Representative pool: **200 / 200 (100%)**.
- Reconstructed trades: **13,861**.

Current risk_target interpretation: the prior downstream multiplier was not 1R sizing. The R-based model now defines `risk_target` as the fraction of account equity lost by a -1R trade.

R-based risk model:

```text
economic_gross_pnl = gross_R × account_equity × risk_target
economic_cost      = cost_R × account_equity × risk_target
economic_net_pnl   = net_R × account_equity × risk_target
```

The pilot uses **PER_STRATEGY_RISK**. A separate portfolio-total-risk policy is documented and tested synthetically; it was not substituted into the historical pilot.

1R @ 1% test:

- -1R: **-$1,000 on $100,000**
- +1R: **+$1,000**
- +2R: **+$2,000**

PER_STRATEGY_RISK: active strategies each receive the configured R budget.
PORTFOLIO_TOTAL_RISK: budget is divided across active strategies; no hidden division was applied to the pilot.

Historical 6,000 portfolios reconstructed: **YES**. Same portfolio IDs, weights, sizes and methods; no generation or search.

Target attainment before breach and over available history is reported in `r_based_target_attainment.csv`. At 1% risk, +10% was reached before a breach by a substantial majority of portfolios; exact counts are in the artifact. This is retrospective and realized-only.

Prop outcomes are in `r_based_risk_frontier.csv` and `r_based_prop_results.csv`, covering 30/60/90/180/FULL horizons and 0.25%–2.00% risk.

Representation comparison is in `representation_comparison.csv`:

- LEGACY_NORMALIZED: dimensionless stream sent to the old interface.
- CAPITAL_SCALED_NORMALIZED: units corrected, percentage path unchanged.
- R_BASED: stop-risk normalized economic stream.

Tests: **PASS (101 tests)**
FAST golden: **PASS**
AUDIT: **PASS**
Portfolio golden: **PASS**
Economic golden: **PASS**
Prop golden: **PASS**
Risk reconstruction golden: **PASS**

Runtime: reconstruction plus matrix artifacts recorded in `performance.json` and `risk_matrix_performance.json`; 13,861 trade rows and 35 frontier cells generated.
Peak RSS: recorded in performance artifacts.

## ROOT CAUSE

The zero-velocity result under the prior model was primarily **MISSING_RISK_NORMALIZATION** combined with **EVALUATOR_POSITION_SIZING**: the evaluator used one price unit and its $10,000 balance only normalized returns. It did not encode 1% stop-risk. The capital-scaled interface fix corrected dollars but could not create risk-sized movement.

## OBSERVED

- Every Library StrategyDefinition has an explicit positive stop multiplier.
- Sampled stops reconstruct to approximately gross_R = -1 on stop exits; costs reduce net_R.
- The R-based reconstruction produces materially meaningful account trajectories and a non-trivial prop frontier, unlike the normalized stream.
- Simultaneous per-strategy risk can exceed a nominal portfolio risk budget; both policies are now explicit.

## INFERRED

- The prior 0% target velocity was not evidence that the strategies had no economic movement; it reflected the absence of stop-risk sizing in the evaluator representation.
- R-based sizing is a defensible downstream research model because stop geometry is causally derivable, but it is not historical evaluator behavior.

## NOT ESTABLISHED

- Future prop-firm pass probability or independent edge.
- Exact MTM/daily-loss behavior; replay remains REALIZED_ONLY.
- Which risk policy or portfolio is preferable.

Strategy Factory V1.8, Grammar V1.7, Strategy Library, replay outputs and existing tags were not modified.
