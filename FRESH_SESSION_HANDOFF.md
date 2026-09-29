# SQX ENGINE — FRESH SESSION HANDOFF

REPOSITORY: `/home/xaume/SQX_ENGINE`  
CURRENT BRANCH: `main`  
CURRENT COMMIT: `a1a4da7`  
PRODUCT OBJECTIVE: maximum real compounded capital growth from multiple bounded PnL engines.  
CURRENT PHASE: Multi-Coin Strategy Factory V1.  
LATEST DECISION: BTC Portfolio Factory supported; expand raw strategy factories across long-history M15 assets.

## Frozen truth

- Economic contract: 1% current-equity strategy risk, 1% standalone heat cap, remaining heat, fees/slippage, no fabricated funding, ruin at equity <= 0.
- Grammar: PRICE_ONLY v1.7; causal next-bar execution.
- BTC split: DEV 2017-08-17→2022-11-07, VAL→2024-02-27, OOS→2025-06-18, LOCKBOX→2026-05-02.
- BTC OOS is burned; BTC LOCKBOX is protected and must remain zero access.

## Proven results

BTC manufactured 50k Random + 200k Genetic unique strategies, admitted 7,350 unique definitions, and supported a 44-candidate exact portfolio frontier. Historic FTMO and early short-history crypto branches are closed/frozen.

## Current artifacts

Read `PROJECT_STATE.md`, `PROJECT_STATE.json`, `NEXT_STEPS.md`, and `runs/reports/crypto_multicoin_factory_v1/`. Raw datasets are under `data/crypto_external/` and are ignored by Git; use catalog hashes.

## Safe next action

Discover and audit all local datasets, freeze the multi-coin temporal policy, then run the per-asset factory with checkpoints. Do not build a multi-coin portfolio yet. Do not access any LOCKBOX. Do not use burned BTC OOS for tuning.

## Verify state

Run `git status --short`, inspect the access ledger, verify catalog hashes, and run `pytest -q` before modifying frozen components.
