# First divergence: SQX-EURUSD-H1-63696db839ee

MT5 entry: `2024-01-02 05:00`; under next-bar causality its signal bar is `2024-01-02 04:00`. Empirical alignment is MT5 timestamp + 0 hours = Python UTC timestamp; the selected offset is 0 hours.

Strategy: LONG, AND, ATR(14), stop_atr=2.5, target_atr=4.0, time_exit=72.

Predicates: `structure.last.2 == 4`, `trend.ema_pair.50.100 > 0`, `trend.ema_slope.200.1 > 0`, `volatility.bb_lower.20.2 < 0`.

At the causal bar, frozen Python logic on the Python feed gives `raw_signal=False`. Frozen Python logic on the MT5 OHLC feed gives `raw_signal=True`. The observed MQL5 EA executed the next-bar entry at 05:00, so the three-way result is Python+Python feed=NO SIGNAL, Python+MT5 feed=SIGNAL, observed MQL5+MT5 feed=SIGNAL.

The first differing layer is therefore **FEED** for this primary case, not an MQL5 implementation mismatch. MQL5 predicate instrumentation is not required for this case.
