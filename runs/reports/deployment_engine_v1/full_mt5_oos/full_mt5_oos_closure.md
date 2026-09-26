# SQX DEPLOYMENT ENGINE V1 — FULL MT5 OOS — FINAL CLOSURE

Evidence SHA256: `fa0bf3ecb976931a9292c5c2ea43e10a712d91b66784141a6848be61ca146b3d`

    The complete UTF-16LE report was parsed into 2,962 transactional deals and
1,481 paired trades, with one separate initial balance row preserved. Net PnL
$5,194.61, deal count, trade count, and final balance $105,194.61 reconcile
exactly. MT5 headline gross profit/loss are $39,359.55/-$34,164.94; the
pairing-derived exit-deal gross split is $40,262.30/-$32,344.16 because 110
HTML-only close pairings are non-unique. This is reported as PARTIAL rather
than silently presented as exact.

The observed result is a characterization of this frozen MT5 period, not a
claim of future profitability or FTMO challenge certification. Exit reasons
without explicit `sl`/`tp` evidence remain OTHER/UNKNOWN. Exact initial-stop
open risk is unresolved from HTML-only evidence; MT5 equity drawdown remains
authoritative at $2,950.94 / 2.74%.

GATES:
{
  "FULL_MT5_OOS_EVIDENCE_INTEGRITY": "PASS",
  "CONFIGURATION_MATCH": "PASS",
  "HTML_PARSE": "PASS",
  "TRADE_LEDGER_RECONSTRUCTION": "PASS",
  "SUMMARY_RECONCILIATION": "PARTIAL",
  "TEMPORAL_ATTRIBUTION": "PASS",
  "STRATEGY_ATTRIBUTION": "PASS",
  "DIRECTION_ATTRIBUTION": "PASS",
  "EXIT_ATTRIBUTION": "PARTIAL",
  "COST_RECONSTRUCTION": "PASS",
  "BALANCE_RECONSTRUCTION": "PASS",
  "PROP_RISK_CHARACTERIZATION": "PARTIAL",
  "PORTFOLIO_MEMBERSHIP_UNCHANGED": "PASS",
  "TRADING_LOGIC_MODIFIED": "NO",
  "STRATEGY_LOGIC_MODIFIED": "NO"
}

FULL_MT5_OOS_COMPLETE
