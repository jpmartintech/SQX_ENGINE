SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2E — FINAL ANALYSIS

The real MT5 diagnostic evidence was analyzed without modifying the captured
CSV files or trading logic. The evidence hashes and row counts are verified in
`round2e_evidence_integrity.json`.

MT5 predicate trace SHA256: `c0097cc4a6fee364a915ca46b468bc5f4798811798194809de68bb5eb5b5c884ba`
MT5 raw signal trace SHA256: `ab39930115413ec0bed55738867da2e246e79e8bfaa59579235e050789b83d27`
MT5 predicate rows: 10,560; raw-signal rows: 231; strategies: 20.
Python MT5-feed expected raw signals: 238.

## Same-input results

There are 10,540 comparable strategy-bars and 32,147 comparable predicates.
Predicate booleans match 31,950 times and differ 197 times (99.3872%). Raw
signals match on 10,527/10,540 comparable bars; Python-only: 10, MQL5-only: 3.

The positive control `SQX-EURUSD-H1-63696db839ee` at signal bar
`2024-01-02 04:00 UTC` is equivalent: all four booleans and the raw signal
are true in both Python-on-MT5-feed and MQL5. Its original Python-feed raw
signal is false, confirming the earlier feed-induced divergence.

The first same-input mismatch is strategy
`SQX-EURUSD-H1-a27691004dcc`, signal bar `2024-01-02 02:00 UTC`, predicate
`structure.break_low.3`: Python value `-0.00043` / true versus MQL5 value
`0.00041` / false. The source is `src/sqx_engine/deployment/templates.py`,
helper `SQX_Structure`; its break modes process the current confirmation
index before returning the swing distance. Frozen Python
`confirmed_structure()` uses the swing state known before the signal bar.
This is a causal same-input implementation defect, not a feed difference.

Additional same-input differences are concentrated in structure break
predicates, compression predicates, and EMA/EMA-slope values near zero. These
must be corrected and recompiled in a subsequent fix round; no speculative
change was made here.

Round 2D unmatched classification: 7 feed-induced, 6 same-input predicate,
14 position/state, and 3 unresolved due non-H1 `00:05` trade timestamps not
represented by the H1 diagnostic evaluation grid.

Tests: 119 passed, 9 warnings. Trading logic modified: NO.

Decision: BLOCKED_ON_IMPLEMENTATION_EQUIVALENCE until the MQL5 structure
break semantics and the remaining same-input indicator differences are fixed,
regression-tested, regenerated, compiled in MetaEditor, and rerun in MT5.

Baseline commit: 8521125
Diagnostic mode implemented: YES
Diagnostic default: OFF (`InpDiagnosticTrace=false`)
Portfolio strategies instrumented: 20
Trace period: 2024-01-01 → 2024-02-01, EURUSD H1
Expected Python+MT5-feed raw signals: 238
Positive control expected result: 63696db839ee signal bar 2024-01-02 04:00 = SIGNAL; entry 05:00
Trading logic modified: NO
Generated Portfolio EA path: deployments/mql5/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5
Expected MT5 trace filename: SQX_portfolio_predicate_trace.csv
Expected raw-signal filename: SQX_portfolio_raw_signals.csv
Tests: 116 passed, 9 warnings
Artifacts: predicate_equivalence/
Commit: this Round 2E preparation commit (reported in final handoff)
Push: origin/main
Working tree: clean after commit

Gates:
{
  "DIAGNOSTIC_TRACE_IMPLEMENTED": "PASS",
  "DIAGNOSTIC_DEFAULT_OFF": "PASS",
  "TRADING_SEMANTICS_PRESERVED": "PASS",
  "CAUSAL_TRACE": "PASS",
  "TRACE_SCHEMA": "PASS",
  "PYTHON_MT5_FEED_REFERENCE": "PASS",
  "PORTFOLIO_MEMBERSHIP_REGRESSION": "PASS",
  "POSITION_OWNERSHIP_REGRESSION": "PASS",
  "RISK_REGRESSION": "PASS",
  "DETERMINISTIC_EXPORT": "PASS",
  "MQL5_COMPILE": "UNRESOLVED"
}
