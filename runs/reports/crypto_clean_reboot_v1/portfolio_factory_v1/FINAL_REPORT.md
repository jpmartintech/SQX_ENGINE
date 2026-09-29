# SQX PROFIT-FIRST PORTFOLIO FACTORY V1 — FINAL STATUS

Starting commit: `2e1aabd`  
Pre-OOS portfolio freeze: `c113baf`  
Search: 50,000 Random + 100,000 Genetic + 27 exact Greedy evaluations.  
Final status commit: pending final artifact commit.

## Input and firewall

- Frozen Library records: 7,634
- Unique strategy hashes: 7,350
- Cross-lineage duplicates removed: 284
- Deterministic DEV+VAL search pool: 120 strategies, both LONG and SHORT
- OOS before freeze: 0
- LOCKBOX before/after: 0/0

The pool reduction was a pre-OOS computational rule based on DEV+VAL trade
support, profitability, direction, and behavioral signature coverage. OOS did
not select strategies, clusters, weights, or portfolios.

## Exact portfolio engine

The engine uses one shared equity curve, chronological trade events, floating
PnL, realized PnL, fees/slippage already present in strategy R, a 1% total
portfolio heat budget split by non-negative weights, and deterministic
same-timestamp exit-before-entry ordering.

Independent reference equivalence: 500/500 PASS. Maximum metric delta:
1.11e-16. Funding is not modeled.

## DEV+VAL search result

The frozen growth/risk frontier contains 44 non-dominated portfolios. The
frontier includes sizes 2 through 50. All selected frontier candidates have
positive DEV and VAL return, PF > 1, positive expectancy, positive minimum
equity, and sufficient trade support.

The strongest observed DEV+VAL growth candidates are Genetic/Greedy mixtures
with DEV returns above 3x and VAL returns up to approximately 0.90x, with
drawdowns varying materially across the frontier. This is a growth/risk
frontier, not one universally optimal portfolio.

## Burned OOS portfolio diagnostic

44 frozen frontier portfolios were tested once on burned OOS data:

- Profitable: 28 / 44, 63.6%
- Median OOS return: +1.11%
- Median OOS PF: 1.008
- Median OOS MaxDD: -19.9%
- Best OOS return: +10.12%

These figures are research diagnostics only and were not used to retune the
frontier.

## BTC-only limitations

Portfolio construction improves the growth/risk frontier, but all strategies
remain exposed to one underlying and shared BTC volatility regimes. Strategy
count therefore overstates independent economic exposure. Additional coins
are a plausible diversification opportunity, but this experiment did not test
them.

Decision: `BTC_PORTFOLIO_FACTORY_SUPPORTED`

Next product action: `MULTI_COIN_STRATEGY_FACTORY`.
