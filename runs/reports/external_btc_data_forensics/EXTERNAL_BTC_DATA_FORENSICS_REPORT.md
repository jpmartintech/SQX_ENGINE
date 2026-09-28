# EXTERNAL BTCUSDT M15 — DATA FORENSICS

External: `data/external_candidate/BTCUSDT_15M_EXTERNAL.csv`; SHA256 `f2ddfd9b85f4e7556474e1ef10f78eebd927a0f0e330785d48b4d08e5b69a20a`; 304,759 rows; 2017-08-17 04:00:00+00:00 → 2026-05-02 14:45:00+00:00.

Canonical SQX: `data/crypto_v12/canonical/BTC_M15_signal_market_binance.parquet`; SHA256 `991290261794eec793f8db1ea6ba74046ff2ba5c21875430bdea64fe76f7b66b`; Binance USD-M Futures; 131,176 rows; 2023-01-01 00:00:00+00:00 → 2026-09-28 09:45:00+00:00.

Matched bars: 116,887. Close correlation: 0.99999961. Exact all-OHLC matches: 0.0000%.

The external file begins in 2017, before the SQX USD-M Futures history. It is therefore not the same SQX futures file; the numerical evidence is consistent with the same BTCUSDT market but a different product, most plausibly Binance Spot. The file has no embedded venue metadata, so that product inference remains conditional.

Classification: **SAME_VENUE_DIFFERENT_PRODUCT**.

Suitable as external validation data: **CONDITIONAL**. It is suitable for source/product validation only after explicitly treating it as a separate signal-market dataset. It must not be described as identical Hyperliquid or SQX Binance Futures execution data.

Strategy accesses to external data: 0

OOS status: UNCONSUMED_FOR_STRATEGY_TESTING
