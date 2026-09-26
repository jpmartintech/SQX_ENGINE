# Position ownership audit — Round 2B

The source filters `SQX_HasPosition` and `SQX_ManagePosition` by symbol and
strategy-specific magic. However, the prompt's example says strategy
`SQX-EURUSD-H1-1320ad51f2e8` logged `TIME_EXIT` while a market sell appeared
to close position #23 opened by `SQX-EURUSD-H1-6d1cb5fa1910`.

That is a potential ownership contradiction, but the actual Journal/ticket
lines are not present in the workspace. It cannot yet be classified as
incorrect selection, misleading logging, magic collision, or netting behavior.
The gate is `UNRESOLVED`; do not advance until the complete ticket/deal chain
is parsed.
