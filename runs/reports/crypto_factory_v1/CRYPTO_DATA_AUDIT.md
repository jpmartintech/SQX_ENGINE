# CRYPTO_DATA_AUDIT

Audit timestamp: `2026-09-28T07:18:43.148156+00:00`
Venue: Hyperliquid

## Result

The read-only API probe is successful for current metadata, recent candles, funding history, asset contexts, and current L2. It is **not sufficient to build the required long historical canonical dataset**: `candleSnapshot` returned a bounded recent sample (observed approximately 5,000 rows) and `fundingHistory` returned a bounded sample (observed 500 rows). No local Hyperliquid historical dataset was found.

The official historical-data documentation describes a requester-pays S3 archive with market-data archives (including L2/asset contexts) and node trade/fill data, but it does not provide a locally available, ready-to-use historical OHLCV + realized funding + OI + mark/oracle dataset. No data was fabricated or downloaded during this audit.

## Field readiness

| Field | Current API | Historical causal V1 readiness | Evidence |
|---|---|---|---|
| BTC/ETH candles | READY (bounded snapshot) | NOT READY | API probe and documented snapshot limit |
| volume/trade count | READY in candle response | NOT READY for long history | candle schema probe |
| realized funding | READY (bounded history) | NOT READY for long history | funding endpoint probe |
| open interest | current asset context only | NOT READY | metaAndAssetCtxs probe |
| mark/oracle/premium | current context/documented semantics | NOT READY historically | official oracle/mark docs |
| L2 | current snapshot | NOT READY historically | l2Book probe; archive requires retrieval |
| liquidations | not established | NOT READY | no authoritative historical field established |

## Decision

`BLOCKED_ON_DATA` for the full Crypto Factory V1 experiment. The additive schemas and economic contract are implemented and tested, but strategy generation and OOS reservation must not begin without a reproducible historical source or an explicitly authorized provider/archive retrieval.

Sources: [official historical data](https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data), [Info endpoint](https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint), [funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding), [fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees), [oracle](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/oracle), [robust price](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/robust-price-indices), [contract specifications](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/contract-specifications).
