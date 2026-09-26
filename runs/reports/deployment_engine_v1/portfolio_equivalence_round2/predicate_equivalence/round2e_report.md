# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2E — FINAL STATUS

MT5 predicate rows: 10560; MT5 raw-signal rows: 231; strategies: 20.

## Same-feed predicate comparison

Comparable strategy-bars: 10540; comparable predicates: 32147.
Boolean matches: 31950; mismatches: 197; match rate: 99.387190%.
Numeric MAE: 0.007730167556766612; max absolute delta: 2.0.

## Same-feed raw signals

Python: 238; MQL5: 231; matches: 10527; Python-only: 10; MQL5-only: 3.

First same-input mismatch: `{'strategy_id': 'SQX-EURUSD-H1-a27691004dcc', 'signal_bar_time': '2024-01-02 02:00:00+00:00', 'predicate_id': 'structure.break_low.3', 'python_value': np.float64(-0.0004300000000001), 'mql5_value': np.float64(0.00041), 'python_result': True, 'mql5_result': False, 'root_cause': 'MQL5 structure.break_low/break_high computes against a swing updated by the current confirmation bar; frozen Python break features use swing state known before the signal bar.'}`.
The first proven implementation defect is the MQL5 structure breakout helper: `SQX_Structure` processes the current signal index before returning `close-lastH/lastL`, while the frozen Python feature bank uses the prior swing state. EMA-based values also show sign-sensitive warm-up differences near zero and compression mismatches; these require a separate correction only after the structure defect is fixed and retested. No trading logic was modified in this analysis.

Positive control: {"strategy_id": "SQX-EURUSD-H1-63696db839ee", "signal_bar_time": "2024-01-02T04:00:00+00:00", "entry_bar_time": "2024-01-02T05:00:00+00:00", "predicates": [{"predicate_id": "structure.last.2", "python_original_result": true, "python_mt5_result": true, "mql5_result": true, "python_mt5_value": 4.0, "mql5_value": 4.0}, {"predicate_id": "trend.ema_pair.50.100", "python_original_result": true, "python_mt5_result": true, "mql5_result": true, "python_mt5_value": 0.0007887245553641, "mql5_value": 0.0007908869015285}, {"predicate_id": "trend.ema_slope.200.1", "python_original_result": false, "python_mt5_result": true, "mql5_result": true, "python_mt5_value": 7.535601671548875e-07, "mql5_value": 9.440197834553744e-07}, {"predicate_id": "volatility.bb_lower.20.2", "python_original_result": true, "python_mt5_result": true, "mql5_result": true, "python_mt5_value": -0.0003716976951892, "mql5_value": -0.0003716976952101}], "python_original_raw_signal": false, "python_mt5_raw_signal": true, "mql5_raw_signal": true, "classification": "DATA_FEED"}

Gates:
{
  "MT5_EVIDENCE_INTEGRITY": "PASS",
  "MT5_PREDICATE_TRACE": "PASS",
  "MT5_RAW_SIGNAL_TRACE": "PASS",
  "SAME_FEED_BAR_ALIGNMENT": "PASS",
  "PREDICATE_ID_EQUIVALENCE": "PASS",
  "PREDICATE_BOOLEAN_EQUIVALENCE": "FAIL",
  "PREDICATE_NUMERIC_EQUIVALENCE": "PARTIAL",
  "RAW_SIGNAL_EQUIVALENCE": "FAIL",
  "POSITION_STATE_CLASSIFICATION": "PARTIAL",
  "RISK_ADMISSION_CLASSIFICATION": "PASS",
  "ROUND2D_UNMATCHED_CLASSIFICATION": "PARTIAL",
  "POSITIVE_CONTROL": "PASS",
  "POSITION_OWNERSHIP_REGRESSION": "PASS",
  "TIME_EXIT_REGRESSION": "PASS",
  "RISK_REGRESSION": "PASS",
  "CONCURRENT_SIGNAL_REGRESSION": "PASS",
  "TRADING_LOGIC_MODIFIED": "NO"
}
