# Regression Tests

Added deployment tests cover:

- exact per-strategy required rate counts for all 20 portfolio members;
- the original S1 failure condition (`EMA(200)` with shift/horizon 1);
- the S13 largest current lookback (`EMA(200)` with horizon 6);
- short-array guards for EMA, ATR, pivot and structure helpers;
- `CopyRates` count checking and series setup;
- `EMPTY_VALUE`/not-ready propagation rather than fabricated zeros;
- portfolio identity, 20-member coverage, deterministic generated code and
  preservation of the individual EA's signal/position structure.

The real MetaEditor/MT5 runtime remains external to WSL and must recompile and
rerun the corrected package.
