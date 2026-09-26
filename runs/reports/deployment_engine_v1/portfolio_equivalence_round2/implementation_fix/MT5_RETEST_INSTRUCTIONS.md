# Round 2F MT5 retest

Copy these regenerated files to the Windows MT5 data directory:

- `deployments/mql5/package/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5`
- all files under `deployments/mql5/package/Include/SQX/`

Compile the EA in MetaEditor and require 0 errors. Run exactly one tester job:

- EA: `SQX_SQX_PROP_02760ECAC8BA`
- EURUSD, H1, 2024-01-01 00:00 through 2024-02-01 00:00
- 1 minute OHLC, FTMO-Demo, 100000 USD, leverage 1:100
- `InpBaseRisk=0.01`, `InpMaxOpenRisk=0.02`
- internal daily/total limits: `0`
- `InpDiagnosticTrace=true`
- `InpDiagnosticFile=SQX_portfolio_predicate_trace.csv`
- `InpDiagnosticRawFile=SQX_portfolio_raw_signals.csv`

Copy the fresh diagnostic CSVs from the Strategy Tester agent Files directory
to `runs/reports/deployment_engine_v1/portfolio_equivalence_round2/predicate_equivalence/`,
preserving the old Round 2E evidence under separate names if needed. Do not run
the 2024-2026 OOS test yet.
