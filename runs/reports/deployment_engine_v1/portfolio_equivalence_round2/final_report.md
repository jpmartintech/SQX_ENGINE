# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2

## Evidence status

Python reference trades: **64** across the 20 frozen members.
MT5 trades: **66 aggregate only**; 132 deals, 48 long and 18 short. No
trade-level MT5 CSV, HTML or execution log exists in the repository.

Matched: **not determinable**. Python-only and MT5-only: **not determinable**.
Trade comparison rows are retained as `AMBIGUOUS`, never as fabricated
matches. Fourteen observed strategy IDs are confirmed portfolio members; six
members are `UNRESOLVED` between inactive and missing evidence.

Portfolio runtime: **PASS**. The tester completed with no runtime crash.
MQL5 compilation: **PASS** from the external MetaEditor evidence.

The source audit confirms deterministic S0→S19 evaluation, weighted base-risk
semantics (`1% × strategy weight`) and magic-number ownership filters. Actual
January signal, exit, volume and 2% open-risk equivalence cannot be certified
without the MT5 trade/deal ledger and signal/order log.

## Required next evidence

Export from MT5 Strategy Tester the deal/order report or `SQX_execution.csv`
with timestamp, strategy ID/comment, magic, direction, volume, entry/exit,
SL/TP, retcode, balance/equity and open risk. Also export the account mode
(HEDGING or NETTING) and EURUSD H1 OHLC/tick data used by the tester.

Decision: `BLOCKED_ON_MT5_EVIDENCE`
