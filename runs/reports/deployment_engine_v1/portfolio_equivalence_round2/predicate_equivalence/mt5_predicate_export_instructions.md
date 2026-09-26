# MT5 predicate trace run

1. Copy the regenerated `deployments/mql5/package/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5` and all `Include/SQX/*.mqh` files into the Windows MT5 data directory.
2. Compile with MetaEditor. WSL cannot certify `MQL5_COMPILE`.
3. Run EURUSD/H1, 2024-01-01 through 2024-02-01, M1 OHLC, deposit 100000, BaseRisk 0.01, MaxOpenRisk 0.02, internal limits 0.
4. Set `InpDiagnosticTrace=true`, `InpDiagnosticFile=SQX_portfolio_predicate_trace.csv`, and `InpDiagnosticRawFile=SQX_portfolio_raw_signals.csv`.
5. Copy both files from MT5 `MQL5/Files` or tester agent `Files` into this directory and run the comparator tooling.

Diagnostics are off by default and use the same `rates[1]` signal bar and `rates[0]` entry bar as production.
