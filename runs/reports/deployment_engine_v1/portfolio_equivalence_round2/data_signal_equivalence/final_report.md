SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2D — FINAL STATUS

Baseline commit: 7bdb31b
Python dataset: data/derived/EURUSD_H1_11d571e8bb3d_143197.csv
Python dataset SHA256: d05762f0ee04a9359c754ff18be4e95575c67bf04b76f202edb184a8963ab21a
Python timestamp convention: UTC-aware H1 bar-open timestamps; available_at is bar close
Python H1 provenance: complete UTC M15→H1 buckets; source `data/cloud/EURUSD_M15.csv`
MT5 H1 data available: NO
MT5 predicate trace available: NO
First divergence strategy: SQX-EURUSD-H1-63696db839ee
First divergence timestamp: 2024-01-02 05:00 MT5 entry
First differing layer: UNRESOLVED_MT5_INPUT
Root cause: not established; exact MT5 H1/predicate evidence is required
Python trades: 64
MT5 trades: 60
Exact causal-bar matches: 47
Feed-equivalent matches: NOT MEASURABLE
True logical mismatches: 0 proven
Downstream-state mismatches: 0 proven
Unresolved mismatches: 30 (17 Python-only, 13 MT5-only)
Code modified: YES — diagnostic-only MQL5 exporter and analysis test; trading logic NO
Trading logic modified: NO
Tests: 114 passed, 9 warnings
Artifacts: complete Python provenance/trace; MT5 export pending
Commit: this Round 2D evidence commit (reported in final handoff)
Push: origin/main
Working tree: clean after commit

## Round 2D gates

{
  "PYTHON_DATA_PROVENANCE": "PASS",
  "MT5_DATA_CAPTURE": "UNRESOLVED",
  "BAR_ALIGNMENT": "UNRESOLVED",
  "TIMEZONE_ALIGNMENT": "UNRESOLVED",
  "RESAMPLING_EQUIVALENCE": "UNRESOLVED",
  "INDICATOR_EQUIVALENCE": "UNRESOLVED",
  "PREDICATE_EQUIVALENCE": "UNRESOLVED",
  "RAW_SIGNAL_EQUIVALENCE": "UNRESOLVED",
  "PORTFOLIO_ADMISSION_EQUIVALENCE": "PARTIAL",
  "DATA_FEED_EQUIVALENCE": "UNRESOLVED",
  "SIGNAL_EQUIVALENCE": "PARTIAL",
  "POSITION_OWNERSHIP_REGRESSION": "PASS",
  "TIME_EXIT_REGRESSION": "PASS",
  "RISK_REGRESSION": "PASS",
  "CONCURRENT_SIGNAL_REGRESSION": "PASS"
}

Operational decision: exact MT5 data export is the next gate.
