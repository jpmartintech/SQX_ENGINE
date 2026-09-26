# First divergence forensics

Primary case: `SQX-EURUSD-H1-63696db839ee`; MT5-only entry at `2024-01-02 05:00`.

The Python reference trace is available in `python_predicate_trace_63696db839ee.csv`. The existing MT5 journal/HTML establishes the trade and its entry, but contains no H1 OHLC, indicator values, predicate values, or raw-signal decision. Consequently the first differing layer is **UNRESOLVED_MT5_INPUT**. It is not valid to call this a feed difference or an exporter bug yet.

Required next evidence: MT5/server-time H1 bars covering at least 2023-11-01 through 2024-02-02, followed by an MT5 predicate trace if aligned OHLC does not explain the divergence.
