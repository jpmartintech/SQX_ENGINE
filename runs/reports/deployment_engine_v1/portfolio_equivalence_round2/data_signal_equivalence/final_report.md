SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2D — MT5 DATA ANALYSIS FINAL STATUS

Baseline commit: af09468
MT5 rows: 1561
MT5 SHA256: 93f48d125d5971ab83a6af248beeb91f2b01571f3f851263fa1bcf1732a8d33b
Python SHA256: d05762f0ee04a9359c754ff18be4e95575c67bf04b76f202edb184a8963ab21a
Best timestamp offset: MT5 + 0h = Python UTC
Bars compared: 1560
Exact OHLC: 1.987%
Differing OHLC: 98.013%
Price-difference statistics: close MAE 0.00004729; P50 0.00001000; P95 0.00017000; P99 0.00096000; max 0.00668000
Missing bars: MT5 8; Python 1
First divergence strategy: SQX-EURUSD-H1-63696db839ee
First divergence MT5 timestamp: 2024-01-02 05:00
Mapped Python timestamp: 2024-01-02 05:00 UTC; causal signal bar 04:00 UTC
Strategy predicates: structure.last.2 == 4; trend.ema_pair.50.100 > 0; trend.ema_slope.200.1 > 0; volatility.bb_lower.20.2 < 0
Python+Python-feed result: NO SIGNAL
Python+MT5-feed result: SIGNAL
Observed MQL5 result: SIGNAL
First divergence root cause: FEED
Python-feed raw signals: 223
MT5-feed raw signals: 238
Feed-induced signal changes: 27
Original Python trades: 64
Observed MT5 trades: 60
Reclassified: feed=7, downstream=0 proven, logical=0 proven, unresolved=23
Algorithmic equivalence conclusion: PASS for the primary divergence and PARTIAL portfolio-wide; no implementation bug demonstrated, but remaining state/admission cases need MQL5 raw-signal evidence.
Historical feed equivalence conclusion: PARTIAL; broker OHLC differs materially enough to alter signals.
Trading logic modified: NO
Tests: 114 passed, 9 warnings
Artifacts: Round 2D data/signal equivalence directory
Commit: this Round 2D MT5 data analysis commit (reported in final handoff)
Push: origin/main
Working tree: clean after commit

Next evidence gate: generic MQL5 predicate/raw-signal export for the remaining non-feed-correlated trade cases.

Gates:
{
  "PYTHON_DATA_PROVENANCE": "PASS",
  "MT5_DATA_CAPTURE": "PASS",
  "BAR_ALIGNMENT": "PASS",
  "TIMEZONE_ALIGNMENT": "PASS",
  "RESAMPLING_EQUIVALENCE": "PARTIAL",
  "INDICATOR_EQUIVALENCE": "PARTIAL",
  "PREDICATE_EQUIVALENCE": "PARTIAL",
  "RAW_SIGNAL_EQUIVALENCE": "PARTIAL",
  "PORTFOLIO_ADMISSION_EQUIVALENCE": "PARTIAL",
  "DATA_FEED_EQUIVALENCE": "PARTIAL",
  "SIGNAL_EQUIVALENCE": "PARTIAL",
  "POSITION_OWNERSHIP_REGRESSION": "PASS",
  "TIME_EXIT_REGRESSION": "PASS",
  "RISK_REGRESSION": "PASS",
  "CONCURRENT_SIGNAL_REGRESSION": "PASS"
}
