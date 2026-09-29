# SQX ENGINE — FRESH SESSION HANDOFF

REPOSITORY: `/home/xaume/SQX_ENGINE`  
CURRENT BRANCH: `main`  
CURRENT COMMIT: `640d176dada32b1d1814542ae4a068e091764f93`  
PRODUCT OBJECTIVE: maximum real compounded capital growth from multiple bounded PnL engines.  
CURRENT PHASE: ready for Multi-Coin Portfolio Factory.  
LATEST DECISION: `MULTI_COIN_RAW_MATERIAL_STRONG`.

## Frozen truth

- PRICE_ONLY v1.7, causal next-bar execution.
- Exact bounded economics: 1% current-equity risk, 1% standalone heat, remaining heat, fees/slippage, no fabricated funding, ruin at equity <= 0.
- New assets: ADA, AVAX, BNB, DOGE, ETH, LINK, SOL, TRX. BTC is historical context and its OOS is burned.
- New-asset LOCKBOX access is zero. Never open any LOCKBOX in the next loop.

## Results

Per-asset campaigns completed at 50k unique Random + 200k unique Genetic. Frozen libraries: ADA 2, AVAX 46,424, BNB 10,978, ETH 7,837, LINK 6,651, SOL 23,847; DOGE and TRX 0. Burned OOS research supports AVAX, ETH, LINK and SOL; BNB is weak and ADA failed its tiny sample. See `runs/reports/crypto_multicoin_factory_v1/`.

## Next action

Build Multi-Coin Portfolio Factory from frozen asset+strategy instances. Use DEV+VAL only for clustering/search; freeze before any future OOS diagnostic. Do not retune strategy factories or select using burned OOS.

## Verify

Run `git status --short`, inspect `PROJECT_STATE.json`, `MULTICOIN_DATA_CATALOG.json`, `MULTICOIN_RAW_MATERIAL.json`, and `DATA_ACCESS_LEDGER.json`; run `pytest -q`. Raw market CSVs are ignored and must never be staged.
