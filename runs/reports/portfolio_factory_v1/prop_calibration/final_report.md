# SQX PORTFOLIO FACTORY — PROP CALIBRATION — FINAL STATUS

Historical 30-day horizon origin: local `FtmoConfig.max_days=30` pilot default, counted event-days; not a verified prop-firm rule. It is now preserved for legacy compatibility and separated from configurable calendar horizons.

Portfolios: **6,000 unchanged historical pilot portfolios**
Risk levels: **0.25%, 0.50%, 0.75%, 1.00%, 1.25%, 1.50%, 2.00%, 2.50%, 3.00%**
Horizons: **30d, 60d, 90d, 180d, FULL**
Total simulations: **270,000**
Label: **RETROSPECTIVE_PROP_RESEARCH**

## RISK FRONTIER

Across all evaluated risk levels and finite horizons, no portfolio reached the 10% challenge target and no daily or total-loss breach occurred. Finite runs terminate as `TIMEOUT`; full-history runs distinguish `DATA_END` where the data ends before a terminal rule.

The detailed matrix is in `risk_frontier.csv`. The target-attainment curve is in `target_attainment.csv`.

## TARGET VELOCITY

No portfolio reached +1%, +2%, +5%, +8% or +10% under the certified economic scaling during the available observed streams. This establishes that the existing 6,000 pilot portfolios have insufficient observed return velocity for the configured 10% target at the tested allocations; it does not establish future performance.

## CHALLENGE → VERIFICATION

The sequential continuation implementation starts Verification strictly after the Challenge target timestamp. No portfolio passed Challenge in this retrospective sample, therefore conditional Verification and both-pass counts are zero. No reselection or reoptimization was performed.

## PORTFOLIO SIZE / WEIGHTING / SEARCH METHOD

Breakdowns are generated in `portfolio_size_analysis.csv`, `weighting_analysis.csv` and `search_method_analysis.csv`. They reuse the same Random, Greedy and Genetic portfolios and do not rank or select a winner.

## FAILURE TAXONOMY

`TIMEOUT` means the configured finite horizon expired. `DATA_END` means the historical stream ended before a terminal rule. `FAIL_DAILY` and `FAIL_TOTAL` preserve diagnostic fields for breach day, daily loss, equity and achieved return where applicable.

## MTM STATUS

**REALIZED_ONLY.** Exact prop-firm daily-loss simulation is not established because floating PnL / MTM is unavailable. The Replay V2 design is documented in `mtm_extension_design.md`.

## OBSERVED

- The original 30-day horizon was a local pilot default, not an external prop rule.
- Increasing the tested risk allocation scales velocity but did not reach 1% in this observed sample.
- The same portfolios, weights and search-method labels were reused; no new search occurred.

## INFERRED

- The current representative pilot has no measurable 10% challenge velocity under the certified economic model, even when the artificial 30-day limit is removed.
- Extending the horizon changes the terminal label from `TIMEOUT` to `DATA_END` when historical data ends, but does not create target attainment.

## NOT ESTABLISHED

- Future prop-firm pass probability.
- Suitability of any risk target or portfolio.
- Exact FTMO/Lucid/Tradeify compliance because MTM and firm-specific rule verification are absent.
- A winning risk level or portfolio.
