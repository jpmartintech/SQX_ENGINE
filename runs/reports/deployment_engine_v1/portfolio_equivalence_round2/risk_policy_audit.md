# Risk policy audit

Base risk is implemented as `InpBaseRisk * portfolio member weight`; the frozen Python weights and the MQL5 requested-risk formula agree. Nominal MT5 stop risk uses EURUSD tick size 0.00001 and tick value $1 per lot.

Reconstructed median MT5/Python intended risk ratio: 0.9635; P5: 0.5368; P95: 1.5750; maximum absolute deviation: 1.7719.

Maximum reconstructed aggregate initial-stop risk: $761.44 (0.7614%) at 2024-01-30 15:00:00. This nominal interval reconstruction is not a substitute for runtime equity/tick-value telemetry, but it is below the configured 2% cap: PASS.

Risk gate: PASS nominally; portfolio advancement remains blocked by the proven position-ownership defect.
