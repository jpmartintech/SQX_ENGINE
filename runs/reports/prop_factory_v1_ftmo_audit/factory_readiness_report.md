# SQX PROP FACTORY V1 — FTMO CONSOLIDATION & RAW MATERIAL AUDIT

Certified/PROP_READY: 8438/8438. Universal economic ledger: 857,538 trades (~690.45 trades/day over the replay span).

The audit is descriptive and bounded; no strategies, predicates, portfolio membership, or MQL5 logic were modified. Five-day measurements use Europe/Paris trading-day-labelled windows.

The rolling five-trading-day median contains 5,815 signals and 5,374 active strategies; this is opportunity capacity, not a promise of admissible trades. The retrospective oracle is explicitly non-tradable and is not a probability of passing. At the 1% reference risk its capped positive-event ceiling reaches the 10%/5% geometric targets in 99.8623% of measured 5D windows; this is an upper bound before path, ownership, daily-loss, max-loss and execution constraints. The current bounded random/greedy/genetic probe is not production discovery.

Generic swap remains unresolved; discovery may use explicit adverse sensitivity scenarios, while finalists require MT5 broker-exact validation. FAST_PROXY versus BAR_EQUITY_REPLAY is not certified by this audit because closed-trade geometry alone cannot supply a valid confusion matrix.

The 120-portfolio random baseline and 48-portfolio greedy/genetic probe are persisted. FAST_PROXY versus BAR_EQUITY_REPLAY is not certified by this audit because the available closed-trade geometry alone cannot supply a valid confusion matrix; a replay-backed calibration sample is required before a large funnel.

Diagnosis: MULTIPLE_LIMITATIONS (raw material is abundant in aggregate, but exact MTM/proxy calibration and broker-exact swap remain production gates). No strategy, portfolio membership, predicate, or MQL5 logic was modified.

Next bounded production action: calibrate FAST_PROXY against BAR_EQUITY_REPLAY on a representative portfolio sample, then launch the bounded FTMO Challenge discovery funnel only if the measured confusion matrix is acceptable.
