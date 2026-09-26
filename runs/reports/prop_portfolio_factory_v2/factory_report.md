# SQX PROP PORTFOLIO FACTORY V2 — FTMO 2-STEP — STATUS

Baseline commit: `cb6610c025a084c359236e462178c656cad1c08b`

This is Stage B smoke output, not funded-account certification. Replay data
contains closed-trade outcomes, not intrabar equity/MTM paths; results are
explicitly `CLOSED_TRADE_PROXY`.

## PROP PROFILE

`FTMO_2STEP_V1`: normalized initial capital `1.0`; Challenge `+10%`;
Verification `+5%`; Daily Loss `5%` of initial capital; static Maximum Loss
`10%`; minimum four trading days; unlimited duration; `Europe/Paris` CET/CEST
day boundaries. Target requires the minimum days and no open position in the
event stream. Right-censored episodes are not failures.

## STRATEGY UNIVERSE

The library contains 12,289 strategies and the frozen certified baseline is
8,438. No standalone certified-ID manifest was present, so V2 persisted a
reproducible manifest of the first 8,438 V1.8 strategies ordered by canonical
hash; provenance is recorded in `strategy_universe.json`.

## SEARCH

- Algorithms: RANDOM, GREEDY, and bounded elitist GENETIC crossover/mutation.
- Sizes: 5, 10, 15, 20, 30, 40, 50.
- Portfolio risk: 0.25%, 0.375%, 0.50%, 0.625%, 0.75%, 0.875%, 1.00%, 1.25%, 1.50%, 2.00%.
- Maximum open risk: 1.0%, 1.5%, 2.0%, 2.5%, 3.0%, 4.0%.
- Concentration caps: 10%, 15%, 20%; infeasible combinations rejected.
- Requested budget: 1,000; canonical-unique evaluations: 974.
- Episodes: 6 deterministic starts from 29 available; 5 earliest events per strategy for the bounded smoke fixture.
- Episodes evaluated: 5,844.
- Runtime: 161.7 seconds; throughput: 6.02 portfolios/s; peak RSS: 837.1 MiB.

All retained smoke candidates were right-censored before target under the
event cap (`P(2-Step)=0`). They validate execution/determinism, not selection.

## BEST OBSERVED FRONTIER

No economically valid frontier is promoted from this capped smoke fixture.

| Candidate | Portfolio hash | Size | Risk | Max open risk | P(Challenge) | P(Verification) | P(2-Step) | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A | `4ed1675757b133f5707b1dbc8723c381be47323babf855530e1e5efd24ad669b` | 50 | 0.750% | 4.0% | 0 | 0 | 0 | RIGHT_CENSORED |
| B | `939e7e5bf7aa6d30d52ce7250199d97f50467badc214773178649803358b6f8a` | 30 | 0.250% | 2.0% | 0 | 0 | 0 | RIGHT_CENSORED |

These rows are descriptive smoke outputs, not “best” production portfolios.

## MONTE CARLO AND ACCOUNT SIZE

Block bootstrap is implemented for blocks 5, 10, and 20 days, 100 runs each,
on the closed-trade proxy stream. It is not exact FTMO equity simulation or a
future-success guarantee. Normalized paths were checked at 10K, 25K, 50K,
100K, and 200K; lot-step, minimum-volume, and margin feasibility remain
unresolved without broker symbol specifications.

## GATES

| Gate | State |
|---|---|
| FTMO_PROFILE | PASS |
| DAILY_LOSS_SEMANTICS | PARTIAL — closed-trade proxy; CET/CEST reset implemented |
| MAX_LOSS_SEMANTICS | PASS |
| TRADING_DAY_SEMANTICS | PASS |
| CHALLENGE_SIMULATION | PASS — proxy |
| VERIFICATION_SIMULATION | PASS — proxy |
| SEQUENTIAL_2STEP | PASS — proxy |
| RIGHT_CENSORING | PASS |
| PORTFOLIO_SEARCH | PASS — bounded Stage B smoke |
| RISK_SEARCH | PASS |
| EXACT_REPLAY | PARTIAL — intrabar equity unavailable |
| MONTE_CARLO | PARTIAL — closed-trade block bootstrap |
| DIVERSITY | PASS |
| ACCOUNT_SIZE_INVARIANCE | PARTIAL — execution feasibility pending |
| STRATEGY_LOGIC_MODIFIED | NO |
| DEPLOYMENT_LOGIC_MODIFIED | NO |

## NEXT BOUNDED RUN

The next production discovery run must use the full event history, all
available episode starts, and exact broker OHLC/tick MTM with floating P/L,
swaps, commissions, and simultaneous-position state. Only after that exact
funnel should ten FTMO Evaluation portfolios be exported for MT5 validation.
The 10K benchmark was not launched: measured smoke throughput projects about
28 minutes before replacing the smoke event cap, while exact MTM inputs are
still absent.
