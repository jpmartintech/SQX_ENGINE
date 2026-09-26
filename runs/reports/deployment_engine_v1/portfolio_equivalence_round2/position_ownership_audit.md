# Position ownership audit

The real Journal reconstructs 21 explicit time-close requests. All 21 close requests close a ticket whose originating strategy differs from the strategy printed by `SQX_POSITION_CLOSE`; the first is ticket #23 (`6d1cb5fa1910`) closed after the `1320ad51f2e8` TIME_EXIT log.

Root cause is reproducible in `src/sqx_engine/deployment/templates.py`: `SQX_ManagePosition` filtered a selected position by magic, then called `CTrade.PositionClose(sym)`, which is symbol-scoped. The selected ticket was not passed. The generated fix calls `PositionClose(ticket)` and logs only a successful ticket close.

Observed cross-strategy closes: 21; orphan repeated TIME_EXIT logs: 191.

Gate: **FAIL — corrected generically; new EA requires MetaEditor recompile and a fresh MT5 run.**
