# Round 2D data and signal analysis

## Python reference

The frozen replay source is `data/derived/EURUSD_H1_11d571e8bb3d_143197.csv` (SHA256 `d05762f0ee04a9359c754ff18be4e95575c67bf04b76f202edb184a8963ab21a`). It contains 143197 UTC bar-open H1 rows from 2003-05-05 03:00:00+00:00 through 2026-04-14 02:00:00+00:00. The canonical derived file was produced from `data/cloud/EURUSD_M15.csv` using `complete_utc_open_buckets_v1`; no timezone shift was applied. `available_at` is the close of each H1 bar. The repository's native H1 file was cross-checked over 143197 rows and is exactly equal for OHLCV, so there is no Python-internal native-vs-derived resampling discrepancy.

## MT5 data status

No exact MT5 H1 OHLC dump or predicate trace exists in the workspace. The corrected journal and HTML provide execution evidence, but not the OHLC input used by `CopyRates`, indicator values, or predicate truth values. Therefore timestamp alignment, timezone/server offset, DST, resampling, and indicator equivalence cannot yet be measured.

The generic non-trading exporter and operator instructions are ready in `deployments/mql5/package/Scripts/SQX_ExportH1Data.mq5` and `mt5_data_export_instructions.md`.

## Implication

The 47 causal-bar matches, 17 Python-only trades, and 13 MT5-only trades are real ledger observations, but the first differing layer is not proven. No feed-equivalent match or true logical mismatch is counted until the MT5 bars are aligned. Ownership, time-exit, risk, and concurrency regressions remain PASS from Round 2C.
