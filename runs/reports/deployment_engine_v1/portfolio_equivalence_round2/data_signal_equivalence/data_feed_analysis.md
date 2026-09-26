# Round 2D MT5 data analysis

The exact MT5 export is intact and hashes to `93f48d125d5971ab83a6af248beeb91f2b01571f3f851263fa1bcf1732a8d33b`. The best empirical timestamp mapping is **MT5 timestamp + 0 hours = Python UTC timestamp**, with 1560 overlapping bars. It is not a timezone assumption: it is the offset that minimizes OHLC error and maximizes exact matches.

After alignment, 31 bars (1.987%) are exact and 1529 (98.013%) differ in OHLC. Close MAE is 0.00004729; P95 absolute component error is 0.00017000; maximum component error is 0.00668000. This is a legitimate broker/feed difference, not a timestamp shift.

The Python control experiment ran all 20 frozen portfolio members on both feeds. Python logic on MT5 OHLC explains the primary MT5-only signal for `SQX-EURUSD-H1-63696db839ee` at the 2024-01-02 04:00 causal bar. See `feed_induced_signal_differences.csv` for the complete raw-signal difference set.

The corrected ownership, time-exit, risk, and concurrency gates remain inherited PASS results. No trading logic was modified.
