# Position ownership audit

The generated EA associates each entry with `SQX-PROP-02760ECAC8BA`, a strategy ID and
strategy-specific magic number. `SQX_HasPosition` and `SQX_ManagePosition`
filter by symbol and that magic number, so the source-level ownership policy
is explicit and a strategy cannot intentionally close another strategy's
magic-matched position.

The MT5 run completed with 66 trades and multiple strategy IDs, but no
trade/deal ledger or position-ticket history was supplied. Cross-strategy
close/SL/TP ownership therefore cannot be empirically verified for January.
Gate: `PARTIAL` pending the MT5 execution CSV or HTML/deal export.
