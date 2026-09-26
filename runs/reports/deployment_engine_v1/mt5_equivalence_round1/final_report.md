# SQX MT5 execution equivalence — Round 1

Strategy: `SQX-EURUSD-H1-1320ad51f2e8`  
Canonical hash: `1320ad51f2e8f9579ad8543f669926cd6fe2b79923be06d2b7b3d6dd9313e765`  
Window: 2024-01-01 through 2024-02-01 UTC

## StrategyDefinition

LONG, EURUSD/H1, four predicates, AND, ATR period 14, `stop_atr=2.0`,
`target_atr=4.0`, `time_exit=24`. The frozen Python engine does define a
price target: `entry + ATR(signal_bar) * target_atr`; it also has a 24-bar
time exit. Exit priority is STOP, TARGET, TIME.

## Results

Python replay produced 5 trades. The operator-provided MT5 run produced 6
trades. Signals before position-state filtering occurred at six bars, but
Python remains in trade 1 until its time exit on 2024-01-08 20:00, while the
pre-fix EA closes it at an artificial near-entry TP and accepts the extra
2024-01-08 17:00 entry.

Signal equivalence: `FAIL` for the observed execution sequence because the
extra MT5 trade changes position-state sequencing; the six raw signal bars
are otherwise consistent with the strategy window.

Entry equivalence: `PARTIAL`. Entry bars align for matched trades; later fill
prices differ by approximately 0.00004, consistent with Ask/Bid execution.

Stop equivalence: `PARTIAL/PASS LOGIC`. Stops match ATR(signal bar) × 2 after
tick normalization within approximately 1e-5–2e-5; MT5 uses broker price
normalization and spread-side fills.

Exit equivalence: `FAIL`. The pre-fix exporter passed
`atr*target_atr/stop_atr*stop` as a target distance even though `stop` was
already `atr*stop_atr`. This produced `target_atr * ATR²`, explaining the
near-entry TPs and six short-lived MT5 trades.

Risk sizing equivalence: `PASS within broker granularity`. With equity
$100,000, 1% risk, tick size 0.00001, tick value $1 and volume step 0.01,
observed volumes imply approximately $998–$999 risk per trade.

Cost-model equivalence: `UNRESOLVED`. SQX replay was run with zero spread and
slippage for logical comparison; MT5 per-trade commission and spread export
were not provided. The reported aggregate MT5 loss cannot be decomposed into
commission/spread from the supplied data.

Data-feed equivalence: `UNRESOLVED`. Both sides report 528 H1 bars and the
SQX feed spans 2024-01-02 through 2024-01-31 UTC. MT5 OHLC/tick export around
signals was unavailable in WSL, so feed differences cannot be fully excluded.

## Correction

Code modified: yes. The shared exporter now emits the correct target distance
`ATR * target_atr` and invokes the common causal position time-exit manager.
Regression tests cover TP translation, time-exit emission, identity and
determinism. Both the individual EA and 20-strategy portfolio EA were
regenerated and the Windows package was updated.

MetaEditor status after regeneration: `MQL5_RECOMPILE = REQUIRED`.

Artifacts:

- `strategy_definition.json`
- `python_trades.csv`
- `trade_comparison.csv`
- `risk_sizing_comparison.csv`
- `exit_semantics.md`
- `data_feed_notes.md`
- `forensics.md`

No strategy discovery, portfolio optimization, reselection, tester execution,
or Demo deployment was performed.
