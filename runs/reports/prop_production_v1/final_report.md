# SQX PROP PRODUCTION PIPELINE V1 — FINAL STATUS

Certified strategy universe: **8,438**

Portfolios generated: **6,000 existing pilot portfolios**
Portfolios evaluated: **6,000**

Production funnel:

- Generated: **6,000**
- Valid: **6,000**
- Redundancy: **4,006**
- Concentration: **4,006**
- Risk: **1,762**
- Prop: **1,758**
- Cost stress: **1,758**
- Robustness: **1,758**
- READY_FOR_PAPER: **20**

The source representative pool is EURUSD/H1 concentrated. This is preserved explicitly in concentration reports; the production cap was configured to permit the certified diagnostic pool, not to claim multi-market diversification.

Account scale:

- 25K: USD PnL scales linearly; return and drawdown percentages unchanged
- 50K: USD PnL scales linearly; return and drawdown percentages unchanged
- 100K: USD PnL scales linearly; return and drawdown percentages unchanged
- 200K: USD PnL scales linearly; return and drawdown percentages unchanged
- Scale invariance: **PASS**

Risk policies: `PORTFOLIO_TOTAL_RISK` exported at 1% base / 2% max-open; `PER_STRATEGY_RISK` remains available for analysis.
Portfolio sizes: **10, 20, 30**
Search methods represented: **RANDOM, GREEDY_DIVERSITY, GENETIC**

READY_FOR_PAPER portfolio IDs: **20**, listed in `ready_for_paper.csv` and exported under `runs/portfolio_exports/`.

Portfolio Library: `data/prop_portfolio_library.sqlite`, 20 persisted portfolios, separate from Strategy Library.

Export status: **PASS**. Account equity remains configurable in each YAML export.

Paper execution contract: **PASS**, realized-only historical contract documented.

Multi-asset readiness: **CONFIG_ONLY / ADAPTER_REQUIRED**. Market specifications are separated; no new asset execution was attempted.

Tests: **104 passed** (9 non-failing numerical/deprecation warnings)
Goldens: Strategy Factory FAST, AUDIT, Portfolio, Economic, Prop and Risk Reconstruction preserved as PASS.
`ACCOUNT_SCALE_INVARIANCE`: **PASS** · `PRODUCTION_EXPORT`: **PASS**

Runtime and RSS: recorded in `performance.json`.

## Operational limitations

- `READY_FOR_PAPER` is an operational gate, not a future profitability claim.
- Historical analysis is `RETROSPECTIVE_PROP_RESEARCH` and `REALIZED_ONLY`.
- Exact daily prop loss under floating PnL requires the future MTM execution/account layer.
- The selected 20 candidates inherit the EURUSD/H1 concentration of the frozen 200-strategy source pool.
- No live broker integration, funded execution, new asset discovery or final portfolio selection was performed.
