# SQX ENGINE — PROJECT STATE

LAST UPDATED COMMIT: `640d176dada32b1d1814542ae4a068e091764f93`  
LAST UPDATED DATE: 2026-09-29  
CURRENT PHASE: Multi-Coin Strategy Factory V1 complete; Multi-Coin Portfolio Factory next.  
CURRENT DECISION: `MULTI_COIN_RAW_MATERIAL_STRONG`

## Product objective

Manufacture multiple profitable, persistent PnL engines, combine them under bounded shared risk, and maximize real compounded capital growth.

## Frozen architecture and contracts

`DATA → PRICE_ONLY Strategy Factory → exact economic validation → Library → Portfolio Factory → Risk Engine → Execution`. Frozen economics: normalized equity 1.0, 1% current-equity risk, maximum standalone open heat 1%, remaining heat for new entries, fees and slippage, no fabricated funding, and ruin at equity <= 0. Execution is causal next-bar. Strategy definitions are hashed deterministically.

## Proven history

The Forex/FTMO branch was closed after insufficient stable forward persistence. Early crypto work found and repaired portfolio aggregation and unbounded per-entry risk defects. The long BTC M15 reboot manufactured 50k Random + 200k Genetic strategies, admitted 7,350 unique definitions, and produced a supported BTC portfolio frontier. BTC OOS is burned research; BTC LOCKBOX remains protected.

## Data and temporal policy

BTC canonical source is `data/external_candidate/BTCUSDT_15M_EXTERNAL.csv` with SHA256 `f2ddfd9b85f4e7556474e1ef10f78eebd927a0f0e330785d48b4d08e5b69a20a`. New local signal data is under ignored `data/crypto_external/`; hashes and manifests are committed. All nine M15 assets pass the mechanical audit and are long-history eligible. Each asset uses its own elapsed-time 60/15/15/10 split; the common intersection is recorded in `TEMPORAL_PROTOCOL.json`.

## This loop result

Eight non-BTC assets completed 50,000 unique Random + 200,000 unique Genetic DEV evaluations. AVAX, BNB, ETH, LINK and SOL produced frozen DEV+VAL libraries; ADA produced two admitted instances; DOGE and TRX produced none. New-asset OOS was opened once after per-asset PRE-OOS freezes as burned research only. `MULTI_COIN_RAW_MATERIAL_STRONG` is based on multiple supported assets, not protected data.

## Burned and protected data

BTC OOS is previously burned. New-asset OOS periods are now burned research diagnostics. Every BTC and new-asset LOCKBOX remains protected with zero access. No OOS result may be used to retune this experiment.

## Do not reopen casually

Do not alter the economic contract, PRICE_ONLY grammar, BTC conclusions, frozen per-asset DEV/VAL memberships, or LOCKBOX firewall. Do not reopen FTMO or old Hyperliquid branches. Do not build weights or leverage from burned OOS.

## Next product action

Open Multi-Coin Portfolio Factory using the frozen per-asset libraries, with event-aligned cross-asset behavioral maps built before optimization. Do not activate Risk Engine or Execution until combined portfolio economics are frozen.

## Fresh-session resume

Read `FRESH_SESSION_HANDOFF.md`, this file, `PROJECT_STATE.json`, `NEXT_STEPS.md`, and `runs/reports/crypto_multicoin_factory_v1/FINAL_REPORT.md`; verify `git status`, hashes, and `DATA_ACCESS_LEDGER.json` before continuing.
