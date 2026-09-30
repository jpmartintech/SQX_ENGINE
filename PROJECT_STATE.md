# SQX ENGINE — PROJECT STATE

LAST UPDATED COMMIT: `74d9ee68cf5d166f9734b6ea1728a9086f77cecd`  
LAST UPDATED DATE: 2026-09-30  
CURRENT PHASE: Multi-Coin Portfolio Factory V1 diagnostic complete.  
CURRENT DECISION: `MULTICOIN_PORTFOLIO_FACTORY_WEAK`

## Product objective

Maximize real compounded capital growth from multiple persistent PnL engines under bounded shared risk.

## Frozen truth

PRICE_ONLY v1.7, causal next-bar execution, exact bounded economics, 1% standalone heat, shared 1% portfolio heat, fees/slippage, no fabricated funding, ruin at non-positive equity. Strategy libraries are frozen per asset. OOS is burned research; every LOCKBOX remains protected.

## Completed result

The primary BTC+AVAX+ETH+LINK+SOL portfolio input reproduced as 92,109 asset-specific strategy instances. A deterministic DEV+VAL-only pool of 200 instances was searched with 50,000 Random, 45 Greedy, and 100,000 Genetic exact shared-equity portfolios. The frozen frontier had 673 records; its burned common-OOS diagnostic had 131 positive (19.5%), median return -43.2%, versus the prior BTC-only burned control of 63.6% positive and +1.11% median return.

## Engine qualification

The multi-asset engine enforces asset ownership, chronological events, floating PnL, current equity, and shared 1% intended heat. Twenty independent Python reference checks passed; 500 fast candidates were searched. The requested full 500-reference audit was computationally disproportionate and is explicitly recorded as incomplete, so this engine is not yet promoted to Risk Engine input.

## Burned and protected data

BTC and new-asset OOS are burned research. Portfolio OOS was opened once after PRE-OOS freeze and is burned diagnostic only. BTC, AVAX, ETH, LINK, SOL, BNB, ADA, DOGE, and TRX LOCKBOX access remains zero.

## Do not reopen casually

Do not use OOS winners, alter frozen strategy libraries, open LOCKBOX, activate Risk Engine, or treat this weak portfolio frontier as validated. Do not silently replace chronological economics with standalone metric aggregation.

## Next product action

Redesign the DEV+VAL portfolio persistence/search layer: build event-aligned strategy PnL/drawdown fingerprints, use them for asset/cluster-aware candidate selection, complete the 500-reference equivalence suite, and rerun Multi-Coin Portfolio Factory before Risk Engine.

## Fresh-session resume

Read `FRESH_SESSION_HANDOFF.md`, `PROJECT_STATE.json`, `NEXT_STEPS.md`, and `runs/reports/crypto_multicoin_portfolio_v1/FINAL_REPORT.md`; verify `git status`, portfolio access ledger, and all per-asset LOCKBOX counters.
