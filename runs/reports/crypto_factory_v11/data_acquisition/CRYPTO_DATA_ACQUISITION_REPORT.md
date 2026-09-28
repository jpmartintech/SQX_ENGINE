# Crypto Factory V1.1 — Data Acquisition Report

## Selected architecture

- Signal market: Binance USD-M perpetual public OHLCV REST.
- Execution venue: Hyperliquid perpetuals.
- Funding source: Hyperliquid public `fundingHistory`, forward-paginated.
- Assets: BTC and ETH.
- Resolution: 1h canonical signal bars.

The Hyperliquid 1h candle endpoint returned no pre-2026 windows during
verification, so it was not treated as a long signal history. Binance Futures
history was selected as an explicitly separate signal-market source. Recent
overlap was measured: return correlation was approximately 0.9994 for both BTC
and ETH; this supports signal research, not byte-identical Hyperliquid
execution replay.

Funding history was recovered from May 2023 through the current endpoint
boundary by pagination. OI, historical mark/oracle series, L2 and liquidation
archives were deferred; they do not block the Tier A/B factory.

OHLCV_READY: TRUE  
FUNDING_READY: TRUE  
ECONOMIC_MODEL_READY: TRUE  
OOS_ACCESSES: 1 (reserved partial-2026 OOS, after freeze)
