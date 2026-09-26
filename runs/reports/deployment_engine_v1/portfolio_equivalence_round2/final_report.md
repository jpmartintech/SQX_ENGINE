# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2B

## Journal forensics status

No MT5 Journal or HTML report file is physically present in the workspace,
`/mnt`, `/tmp` or `/home/xaume`. The only new execution evidence available is
the textual examples in the request. Therefore no complete parser run or
66-trade reconstruction can be truthfully claimed.

The parser is available at `scripts/parse_mt5_journal.py` and is ready to
ingest the actual Journal once copied into the repository. The current
`mt5_journal_trades.csv` explicitly records `JOURNAL_NOT_PRESENT`; it does not
invent the 66 trades.

## Available conclusions

- Runtime: PASS, based on the supplied tester result (66 trades / 132 deals).
- Python reference: 64 trades.
- Journal reconstructed: 0; not available for ingestion.
- HTML cross-check: not executed; HTML not available.
- Portfolio IDs in examples: valid members, but complete membership cannot be
  certified from a partial list.
- Base-risk examples are directionally consistent with `1% × weight` sizing,
  but the full distribution cannot be calculated.
- Simultaneous EURUSD positions suggest HEDGING, but account mode is not
  certified without the tester account-mode field or complete ticket export.
- The reported `TIME_EXIT`/position #23 sequence is a potential ownership
  contradiction. It is not classifiable without the actual ticket/deal lines.

## Blocking evidence

1. the complete MT5 Journal text containing the SQX events and ticket/deal
   lines;
2. the MT5 HTML report containing the 66 trade / 132 deal rows.

After ingestion, correlate `SQX_ORDER_SENT`, order, deal, position, stop,
target and `SQX_POSITION_CLOSE` records before changing any code. No exporter
or runtime code was modified in Round 2B.

Decision: `BLOCKED_ON_MT5_EVIDENCE`
