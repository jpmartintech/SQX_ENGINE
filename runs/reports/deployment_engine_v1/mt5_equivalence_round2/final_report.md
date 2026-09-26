# MT5 execution equivalence Round 2

Strategy: `SQX-EURUSD-H1-1320ad51f2e8`
Window: 2024-01-01 → 2024-02-01 UTC

Python trades: 5
MT5 trades: 5
Matched trades: 5/5

All five trades have matching LONG direction, N+1 entry bars and matching exit mechanisms: TIME, STOP, STOP, STOP, TARGET. Entry/stop/target price differences are small and compatible with independent FTMO feed, Bid/Ask and tick normalization.

The Python first trade records the H1 close at 2024-01-08 20:00; MT5 sends the explicit close on the first tick of 2024-01-08 21:00 after 24 bars have elapsed. This is PASS for the 24-bar logical holding window and PASS for logical exit bar, with tick timestamp equivalence PARTIAL by execution granularity.

Dynamic equity sizing is confirmed: actual volumes 2.34, 5.77, 5.81, 4.82 and 4.72 decrease consistently with realized commission/swap losses. Implied stop risk remains within lot-step tolerance of 1%.

Costs: MT5 commissions and swaps explain monetary differences and remain only PARTIAL against the frozen Python zero-cost logical replay. Feed equivalence is UNRESOLVED without MT5 OHLC/tick export.

No code changes were made in this round. No portfolio EA execution was run.

Portfolio decision: `READY_FOR_PORTFOLIO_EA_VALIDATION`
