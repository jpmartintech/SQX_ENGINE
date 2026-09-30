# SQX ENGINE — FRESH SESSION HANDOFF

REPOSITORY: `/home/xaume/SQX_ENGINE`  
CURRENT BRANCH: `main`  
CURRENT COMMIT: `74d9ee68cf5d166f9734b6ea1728a9086f77cecd`  
PRODUCT OBJECTIVE: maximum real compounded capital growth under bounded shared risk.  
CURRENT PHASE: Multi-Coin Portfolio Factory redesign required.  
LATEST DECISION: `MULTICOIN_PORTFOLIO_FACTORY_WEAK`.

## Frozen truth

- Primary libraries: BTC, AVAX, ETH, LINK, SOL; BNB excluded from primary search.
- Exact economics: shared portfolio equity, total intended heat 1%, current-equity sizing, fees/slippage, no fabricated funding, ruin at equity <= 0.
- Strategy OOS and portfolio OOS are burned research. All LOCKBOX periods remain protected with zero access.

## Completed portfolio diagnostic

92,109 strategy instances were reproduced. A 200-instance DEV+VAL-only pool was searched with 50,000 Random, 45 Greedy, and 100,000 Genetic exact portfolios. The frozen frontier had 673 records; 131 were positive in burned OOS (19.5%), median return -43.2%. Prior BTC-only control: 44 frozen portfolios, 63.6% positive, +1.11% median return. Multi-coin did not improve the control.

## Known limitation

Only 20 independent Python reference replays completed because the full 500-reference audit was too slow. The next loop must finish the equivalence suite and implement event-aligned DEV+VAL PnL/drawdown fingerprints before selecting a new pool.

## Next action

Redesign and rerun Multi-Coin Portfolio Factory using DEV+VAL behavioral persistence. Do not use burned OOS, activate Risk Engine, or open LOCKBOX.

## Verify

Run `git status --short`, inspect `PROJECT_STATE.json`, `runs/reports/crypto_multicoin_portfolio_v1/FINAL_REPORT.md`, and both access ledgers; run `pytest -q`.
