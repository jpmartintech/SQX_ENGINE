SQX DEPLOYMENT ENGINE V1 — MQL5 — FINAL STATUS

REAL METAEDITOR FEEDBACK ROUND 1

Original compile: 7 errors / 0 warnings.
Root causes: invalid `static` on the generated global strategy function and `SQX_LoadRates` declared `MqlRates&` instead of `MqlRates&[]`, causing the ArraySetAsSeries/CopyRates cascade and line-25 expression error.
Exporter/common-library fixes: removed invalid `static` and corrected the shared MQL5 array signature; closed-bar `shift=1` causality preserved.
Regression tests: MqlRates array signature, ArraySetAsSeries/CopyRates, no invalid static functions, single/portfolio invariants, identity, determinism and coverage.
EAs regenerated: single strategy and 20-strategy portfolio.
Package updated: `deployments/mql5/package`.

Strategy Factory: V1.8 preserved
Strategy Library: 12289
Portfolio Library: data/prop_portfolio_library.sqlite

Deployment backend: MQL5
Library export coverage: 12289/12289
Certified universe export coverage: 8438/8438 (100%; baseline certified universe preserved)
READY_FOR_PAPER export coverage: 20/20 portfolios; 100% of selected portfolio strategies

Predicates supported: explicit V1.7 registry
Predicates unsupported: 0 in READY_FOR_PAPER sample

Single strategy exported: SQX-EURUSD-H1-1320ad51f2e8
EA path: /home/xaume/SQX_ENGINE/deployments/mql5/Experts/SQX/SQX_SQX_EURUSD_H1_1320ad51f2e8.mq5
Portfolio exported: yes
Portfolio ID: SQX-PROP-02760ECAC8BA
Strategies: 20
EA path: /home/xaume/SQX_ENGINE/deployments/mql5/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5

R sizing: PASS
Portfolio risk manager: PASS
Account-size independence: PASS
Multi-symbol: architecture ready; current certified portfolio is EURUSD
Multi-timeframe: M15/H1/H4 mapping implemented
Hedging/netting handling: documented and logged; independent identities require compatible account mode
Logging: CSV + Journal events
MT5 importer: PASS
Comparison engine: PASS
MetaEditor compiler available: NO
Compile status: NOT_EXECUTED — compiler unavailable on Linux/WSL
Strategy Tester: READY after Windows MetaEditor compile
Demo package: READY, credential-free
Tests: 108 passed
Goldens: existing suite PASS
Runtime: 0.600s
Peak RSS: 173.1 MiB
Git commit: pending until this fix round is committed
Push: pending until this fix round is committed
Working tree: pending until this fix round is committed

OPERATIONAL STATUS:

READY_FOR_MT5_STRATEGY_TESTER
