SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2C — FINAL STATUS

Corrected Journal parsed: YES — UTF-16LE, 651 lines; 120 deals and 60 complete trades.
Corrected HTML parsed: YES — 120 order/deal rows; reconciles with the Journal.

MT5 corrected result: 60 trades, 120 deals, net PnL -614.00 USD, maximum equity drawdown 0.72%.
Python reference: 64 frozen trades.
Trade matching by strategy, direction and causal H1 entry bar: 47 matched, 17 Python-only, 13 MT5-only, 0 ambiguous. The net difference is therefore -4 trades, not a single isolated pair.

Ownership fix:

- Before: 21 cross-strategy closes and 191 orphan TIME_EXIT logs.
- After: 0 cross-strategy closes and 0 orphan TIME_EXIT logs.
- Control: `1320...` now closes ticket #22 owned by `1320...`; the broken run closed ticket #23 owned by `6d1...`.
- Corrected TIME_EXIT events: 7/7 owned closes.

The remaining Python/MT5 differences are signal-stream and downstream state differences. The first confirmed MT5-only entry is `63696db839ee` at 2024-01-02 05:00; exact predicate/feed causality cannot be proven without the MT5 OHLC export. Python-only and MT5-only rows are preserved in `trade_comparison_fixed.csv`; they are not relabeled as feed differences without evidence. Consequently signal equivalence remains PARTIAL and the full-OOS gate is not advanced in this round.

Risk reconstruction under the frozen EURUSD nominal tick assumptions gives maximum open stop risk of $216.89 / 0.2169%, below the configured 2% cap. Base-risk semantics remain 1% multiplied by frozen portfolio weight.

Account behavior is HEDGING-compatible through independent same-symbol tickets. The Journal does not print the numeric `ACCOUNT_MARGIN_MODE` enum, so this is behavioral compatibility rather than an explicit enum capture.

MQL5 compile: PASS by provenance — the corrected EX5 was loaded by the Tester and completed the exact January configuration; the observed ticket #22 close proves the corrected runtime was executed.

Code modified this round: NO trading logic change. Parser/report tooling and retest artifacts were added; the existing generic `PositionClose(ticket)` fix remains unchanged.

Tests: full pytest 113 passed.

See `equivalence_gates_fixed.json` and the CSV artifacts in this directory for the complete gate state and trade-level evidence.

Decision: BLOCKED_ON_MT5_EVIDENCE — the corrected Journal/HTML prove ownership, but the indispensable MT5 H1 OHLC/predicate evidence needed to classify the remaining first causal signal divergences is not present.
