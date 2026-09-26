# Portfolio risk policy audit

The frozen portfolio contains 20 members and weights
sum to 1.000000000000. The generated MQL5
policy requests `base_risk × strategy_weight`, i.e. 1% is the total weighted
portfolio budget, not 1% per strategy. The common risk manager compares the
requested risk with remaining `max_open_risk` capacity and passes the reduced
risk into volume sizing.

The Python reference ledger contains 64 independently
replayed strategy trades. The MT5 ledger supplied only aggregate PnL and trade
counts, so actual volume, tick value, equity-at-entry and open-risk-before/
after cannot be reconstructed. No claim of empirical 2% compliance is made.
