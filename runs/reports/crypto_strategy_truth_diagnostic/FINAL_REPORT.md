# SQX CRYPTO STRATEGY TRUTH DIAGNOSTIC — FINAL STATUS

Starting commit: `6dc5991`

Frozen strategies: 63; modified: 0; portfolio optimization: 0; LOCKBOX accesses: 0/0.

## Economic truth

The exact evaluator interprets `0.01` as one total fixed-fractional risk budget per entry, split by strategy weights. It is not a hard 1% portfolio-heat cap and it does not cap the loss magnitude of an R value above 1. Concurrent positions can retain prior risk while new entries allocate additional current-equity risk; negative equity is possible when realized/floating R losses exceed cash.

## Individual truth

Aggregate PF>1: 37; aggregate expectancy>0: 40; aggregate return>0: 37; economically valid after ruin: 0; ruin: 63. Segment PF-positive DEV/VAL/OOS: 35/34/10. Positive expectancy DEV/VAL/OOS: 37/34/10. Positive 3/3: 0.

All 63 records differed materially from exact DEV economic PF/MaxDD because stored Library PF is R-space/trade-statistic based while the exact portfolio evaluator weights realized PnL by evolving risk and marks floating equity. Expectancy R and trade count agree, but that does not make the economic systems equivalent.

## Temporal and independence evidence

The exact OOS median PF is 0.608; the exact DEV median PF is 1.057. DEV→OOS expectancy rank correlation is -0.365. Behavioral clustering produced 36 deterministic clusters at similarity threshold .65; correlation effective rank was 16.74. Pairwise daily PnL median correlation was 0.004; pairwise loss correlation median was -0.003.

## Diagnosis

`MULTIFACTORIAL`: economic semantics are not equivalent to the stored Library metrics, the apparent edge deteriorates sharply into OOS, and the 63 strategies have materially fewer independent dimensions than their count suggests. This is diagnostic burned-data evidence only; no Library, strategy, portfolio, or protected holdout was changed.
