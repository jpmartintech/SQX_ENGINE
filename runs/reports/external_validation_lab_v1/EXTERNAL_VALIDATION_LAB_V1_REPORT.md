# SQX EXTERNAL VALIDATION LAB V1

Classification: **CRYPTO_STRATEGY_EDGE_TEMPORALLY_MIXED**.

## Protocol

The frozen BTC M15 PRICE_ONLY universe was replayed without modification. No indicators, predicates, thresholds, strategy selection rules, portfolio optimization, or leverage were changed. Volume was retained as metadata only.

Regions were frozen before strategy evaluation:

- E0: 2017-08-17 → 2018-12-31 context only
- E1: 2019-01-01 → 2020-12-31 backward holdout
- E2: 2021-01-01 → 2022-12-31 backward holdout
- X1: 2023-01-01 → 2025-12-31 cross-product comparison
- X2: 2026 known-history diagnostic, not accessed

## Evaluator

Reference/Fast equivalence passed on 10 representative strategies. Entry timestamps, exits, trade counts, R values, and equity outputs matched.

## Cross-product results

The external and SQX Futures feeds had median entry/trade Jaccard agreement of 40.74%. Economic performance was directionally related but not identical:

- External X1 median PF: 1.156
- Futures X1 median PF: 1.159
- External X1 median expectancy: +0.086R
- Futures X1 median expectancy: +0.021R
- Positive on both: 105/183
- Rank Spearman correlation: 0.701
- Top-quartile overlap: 55.2%
- Top-decile overlap: 33.3%

Fixed aggregate controls were positive on X1 external (+14.14% for ALL_EQUAL) and only modestly positive on X1 Futures (+1.27%). This is cross-product evidence, not independent temporal evidence.

## Backward temporal transport

E1 was weak: 44/183 positive strategies, median PF 0.920, median expectancy -0.091R. The ALL_EQUAL fixed aggregate returned -17.41% with 19.3% MaxDD.

E2 was mixed: 78/183 positive strategies, median PF 1.028, median expectancy -0.019R. The ALL_EQUAL fixed aggregate returned -4.67% with 5.95% MaxDD; the predeclared TOP_N control returned +3.52% with 6.81% MaxDD.

The joint evidence is therefore mixed: cross-product portability is partial, while backward temporal transport is weak in E1 and mixed in E2. The result does not support a robust externally validated edge claim.

Strategy accesses: E1=183, E2=183, X1=183, X2=0. Other external crypto accesses=0.
