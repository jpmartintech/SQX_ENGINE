# SQX ENGINE — PROJECT STATE

LAST UPDATED COMMIT: `a1a4da7`  
CURRENT PHASE: Multi-coin Strategy Factory V1  
CURRENT DECISION: BTC portfolio factory supported; multi-coin factory expansion beginning.

## Product objective

Manufacture multiple profitable, persistent strategy engines, combine them with bounded shared risk, and maximize real compounded capital growth.

## Frozen economic contract

Initial equity is normalized to 1.0. Strategy risk is 1% of current equity, with maximum standalone open heat of 1%; remaining heat controls new entries. Fees and slippage are modeled, funding is not fabricated, and equity <= 0 is ruin.

## Research method

PRICE_ONLY v1.7, causal next-bar execution, deterministic hashes, exact reference/fast equivalence, elapsed-time DEV/VAL/OOS/LOCKBOX firewalls, and Random/Genetic manufacturing.

## Completed phases

- Forex/FTMO branches were frozen after insufficient stable forward persistence.
- Early crypto work exposed and fixed portfolio aggregation and unbounded-risk defects.
- BTC long-history reboot manufactured 50k Random + 200k Genetic strategies.
- BTC Strategy Factory: `PRICE_ONLY_FACTORY_SUPPORTED`; 7,350 unique admitted definitions.
- BTC Portfolio Factory: `BTC_PORTFOLIO_FACTORY_SUPPORTED`; exact 50k Random + 100k Genetic portfolio search and 28/44 profitable burned-OOS diagnostics.

## Data status

BTC canonical signal dataset is `data/external_candidate/BTCUSDT_15M_EXTERNAL.csv`, SHA256 `f2ddfd9b85f4e7556474e1ef10f78eebd927a0f0e330785d48b4d08e5b69a20a`.
Additional local signal datasets are discovered under `data/crypto_external/`; raw data is ignored by Git and only hashes/manifests are committed.

## Burned and protected data

BTC OOS (2024-02-27 → 2025-06-18) is burned research evidence. BTC LOCKBOX (2025-06-18 → 2026-05-02) remains protected with zero access. New-asset OOS and LOCKBOX status is controlled per asset by the current experiment ledger.

## Current experiment

Discover and audit additional M15 datasets, freeze a common temporal policy, reuse the BTC factory without semantic changes, manufacture 50k Random + 200k Genetic per eligible asset, freeze before VAL and OOS, and measure multi-underlying raw material. Do not build the multi-coin portfolio in this phase.

## Do not reopen casually

Do not change the economic contract, BTC split, PRICE_ONLY grammar, burned BTC conclusions, or protected LOCKBOX. Do not use OOS to select strategies, clusters, weights, or fitness. Do not reopen FTMO or old Hyperliquid branches.

## Expected next steps

Complete this multi-coin factory. If raw material is supported, freeze per-asset libraries and open Multi-Coin Portfolio Factory, then validate combined economics, activate Risk Engine, and define execution.

## Fresh-session resume

Read `FRESH_SESSION_HANDOFF.md`, `PROJECT_STATE.json`, `NEXT_STEPS.md`, and the latest `runs/reports/crypto_multicoin_factory_v1/FINAL_REPORT.md`. Verify `git status`, the data catalog, and the access ledger before taking action.
