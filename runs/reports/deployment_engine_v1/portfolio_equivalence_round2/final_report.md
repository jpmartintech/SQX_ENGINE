SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2B — FINAL STATUS

Journal file parsed: YES — UTF-16LE, 930 lines.
HTML file parsed: YES — 132 order rows (66 entries + 66 exits).
MT5 trades reconstructed: 66; MT5 deals: 132.
Python trades: 64.

The net difference 64 vs 66 is not a single pair: 50 chronology/strategy matches, 14 Python-only rows and 16 MT5-only rows. The exact lists are persisted in `trade_comparison.csv`; the additional MT5 entries include strategy `63696db839ee`, while Python-only entries include `4c92b8eb8610`, `59d9b5d3a639`, `636292a9084a`, and `6682b7a6ec07`. Without the MT5 H1 bars and before correcting ownership, the per-row signal discrepancy cannot be attributed uniquely to feed versus logic.

TIME_EXIT ownership: FAIL. All 21 explicit time-close requests reconstructed to a different originating ticket owner; 191 subsequent TIME_EXIT messages are orphan/repeated logs. The first proven case is requester `1320ad51f2e8`, ticket #23 owner `6d1cb5fa1910`.

Actual account behavior: HEDGING-compatible independent tickets; simultaneous same-symbol positions and ticket-specific exits prove independent position representation.

Base risk: PASS — 1% multiplied by frozen member weight. Maximum nominal reconstructed open stop risk: $761.44 (0.7614%), below 2% under the stated EURUSD tick assumptions.

Code modified: YES. Generic fix: `CTrade.PositionClose(ticket)` in the common MQL5 execution template, with success-only TIME_EXIT logging. Individual and portfolio EAs/package regenerated; MetaEditor recompilation is required.

Tests: full pytest 113 passed; deployment tests 9 passed in this turn.

Artifacts: all required CSV/MD/JSON files in this directory, plus `scripts/portfolio_round2b_forensics.py` and `scripts/portfolio_round2b_report.py`.

Decision: STOP before OOS.
