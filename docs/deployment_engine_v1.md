# SQX Deployment Engine V1 — MT5 protocol

The deployment boundary consumes immutable `StrategyDefinition` objects and
the existing portfolio library. The MQL5 backend has an explicit predicate
registry and rejects unknown features with `EXPORT_REJECT_UNSUPPORTED_PREDICATE`.
Signal evaluation occurs once per symbol/timeframe new bar using shift 1; entry
is sent on the next available bar/tick. MT5 supplies fills, positions, equity,
margin and floating PnL.

`SQX_RiskVolume` uses equity, ATR stop distance, tick size/value, contract
metadata and volume limits from the live symbol. Portfolio open risk is derived
from each position's entry, current stop and volume. `SQX_CheckPortfolioRisk`
returns full, reduced or rejected decisions.

Run `sqx deployment export` and then `deployments/mql5/deploy_mql5.ps1`. The
Linux environment cannot compile MetaEditor; compilation must be recorded from
Windows MetaEditor and is therefore `NOT_EXECUTED` in this environment.

The tester gate is translation-only: compare signal timestamp, direction,
entry, stop and exit records against SQX with explicit price tolerances. It is
not a portfolio reselection or optimization campaign.
