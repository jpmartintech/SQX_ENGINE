# SQX EXACT EQUITY REPLAY V1 — REPORT

Baseline: `79e1f68979be745badbd88b5e3c1febe2c7f2869`

The replay layer is implemented at bar resolution. M15 is used to mark H1/H4 positions and M15 positions. It supports normalized floating P/L, realized balance, daily equity floors in Europe/Paris, static maximum loss, open-risk aggregation, costs, simultaneous positions, and conservative OHLC path probes.

The MT5 reference portfolio contains 1481 positions and was replayed against EURUSD M15. Reconstructed normalized return was 0.05221770 versus MT5 0.05194610; this is calibration evidence, not a claim of exact broker replication. The replay is not tick-exact and its bar adverse path is conservative. Ambiguous stop/target hits: 4.

Critical coverage limitation: the general 12,289-strategy replay has entry/exit outcomes but no universal initial-stop geometry. Explicit stop geometry currently covers 13861 reconstructed positions across 200 strategies. Therefore arbitrary 8,438-strategy exact FTMO replay is not yet certifiable.

Costs: commission and swap are exact where present in the MT5 ledger; spread is unresolved from the normalized trade ledger; generic-library swap remains unresolved. No external data was downloaded.

The next step before FTMO discovery is to produce/attach universal stop geometry and cost metadata for the certified universe, then rerun this replay with exact strategy position ledgers.
