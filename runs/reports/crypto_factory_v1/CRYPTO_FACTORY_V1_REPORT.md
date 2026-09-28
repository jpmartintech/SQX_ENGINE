# SQX CRYPTO FACTORY V1 — DATA-BOUNDARY REPORT

## Conclusion

`BLOCKED_ON_DATA`. This run intentionally stopped before strategy generation.
The official Hyperliquid API was probed read-only and confirmed current
metadata, recent candles, bounded funding history, current asset contexts,
and current L2. It did not provide the long, synchronized historical dataset
needed for causal walk-forward research. No historical data were fabricated,
and no OOS period was opened.

The official archive is a possible future source, but it requires explicit
requester-pays/archive access and retrieval work. Its documented contents do
not constitute a ready local OHLCV + realized funding + OI + mark/oracle
dataset. That boundary must be resolved before data quality, feature value,
strategy edge, or portfolio edge can be concluded.

## What was implemented

- Additive UTC, 24/7 canonical Crypto bar validation and causal availability
  checks.
- Deterministic complete-grid resampling without gap filling.
- `CryptoEconomicSpecV1` with Hyperliquid-style linear perpetual fields.
- Separate maker/taker fee assumptions, slippage, realized funding PnL, and
  explicit isolated liquidation approximation.
- Read-only official API audit and machine-readable provenance artifacts.

## What was not started

Strategy generation, information ablation, walk-forward splits, portfolio
search, leverage selection, final OOS, deployment, and live order pathways.

## Re-entry condition

Provide or authorize a reproducible historical source with synchronized
completed candles, realized funding settlements, and documented availability
for any OI/mark/oracle/premium fields used by the factory. Then rerun the data
audit before opening any OOS period.
