# SQX UNIVERSAL STRATEGY ECONOMICS V1 — REPORT

Certified strategies: 8438. Geometry rows: 857538. Geometry ready: 8438. Profile-cost ready: 8438.

The frozen evaluator source is preserved: ATR(14) on the causal signal bar; stop distance ATR×stop_atr; target distance ATR×target_atr; time exit at the frozen held-bar condition; profile cost `(spread + slippage)` once per completed trade. The universal ledger is derived from the immutable replay trades and existing market data, not from strategy optimization.

Existing geometry comparison: 9832 comparable rows; exact matches 9832; tolerance matches 9832; mismatches 0; max stop delta 2.220446049250313e-16.

All 8438 strategies resolve to one of the 21 approved execution profiles. Generic spread/slippage are PROFILE_MODEL assumptions; commission is represented by the frozen profile friction rather than a separate charge; generic historical swap is UNRESOLVED and broker-exact swap remains MT5 finalist evidence.

MT5 reference remains 1481 trades with Python return 0.05221770 vs MT5 0.05194610; this is a regression/calibration reference.

Universal replay supports arbitrary supplied economic geometry and multi-market/multi-timeframe bar marking. The certified replay source did not contain universal stop geometry as a native field; V2 reconstructs it causally from the frozen evaluator ATR model. The entry-to-previous-dataset-row join resolves calendar/DST gaps and yields 8438/8438 valid strategies. Generic swap remains unresolved and must be sensitivity-tested; this is allowed for LEVEL_B discovery and broker-exact MT5 remains mandatory for finalists.

Decision: UNIVERSAL_STRATEGY_ECONOMICS_V1_READY for profile-cost-based FTMO discovery, with broker-exact costs reserved for MT5 validation.
