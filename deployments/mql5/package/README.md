# SQX Deployment Engine V1 — MT5 package

Copy `Experts/SQX` and `Include/SQX` into the active MT5 data directory under
`MQL5/`. Compile the selected EA in MetaEditor, then run it in Strategy Tester
with the symbol/timeframe data required by the portfolio. The EA writes
`SQX_execution.csv` to `MQL5/Files` and never contains broker credentials.

The generated portfolio is selected deterministically from the certified
`READY_FOR_PAPER` library by ascending `portfolio_id`. Verify account mode
(NETTING/HEDGING) and symbol availability before Demo deployment.
