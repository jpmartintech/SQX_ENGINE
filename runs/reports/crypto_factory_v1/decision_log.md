# Decision log

## CRYPTO_V1_DATA_AUDIT_001

- Evidence: read-only official API probes succeeded for metadata, recent candles, funding, current contexts, and L2.
- Constraint: candle and funding responses are bounded; no local historical Hyperliquid dataset exists.
- Decision: implement only additive data/economic contracts and stop before generation.
- Falsifier: a reproducible authorized historical source with causal candles, realized funding, and required market fields.
- OOS accesses: 0.
