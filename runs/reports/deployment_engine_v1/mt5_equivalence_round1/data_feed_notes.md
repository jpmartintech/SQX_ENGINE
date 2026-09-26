# Data/feed notes

The SQX EURUSD H1 derived dataset contains 528 bars from 2024-01-02 00:00 UTC through 2024-01-31 23:00 UTC, matching the operator-reported MT5 bar count. MT5 OHLC bars/tick export was not available in the Linux workspace, so exact per-bar feed comparison around fills and exits is unresolved. The observed +4e-5 entry differences after the first trade are consistent with Ask/Bid spread and are classified as broker execution/data-feed evidence, not signal logic. Export MT5 H1 OHLC and tick/commission details for the next gate.
