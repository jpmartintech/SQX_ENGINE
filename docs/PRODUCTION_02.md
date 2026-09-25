# PRODUCTION_02 — frozen V1.8, expanded execution inputs

Factory base: `16a70ec0db6d58f8adb51ec8ae7caa361e139003`. Grammar V1.7.
Policy remains `PRODUCTION_2016_2026_V1`: Development [2016,2022), Validation
[2022,2024), OOS from 2024 through the last available closed bar. Pre-2016 bars
remain reserved and are not used by this production. No engine code changes.

## Evidence and approval of execution assumptions

The primary existing repository evidence is the preserved EURUSD V1.8 profile.
The project data source also contains explicit historical instrument profiles at
`/home/xaume/proyectos/sqx_lite/market_profiles/profiles.yaml`. The accompanying
`market_profiles/__init__.py` documents `fee_pips` as round-trip friction and
`slippage_pips` as per-side slippage. Their hashes and relevant profile snapshot
are retained in `configs/execution_profiles/` and the execution manifest.

V1.8's Python and Numba kernels deduct `(spread + slippage) * cost_multiplier`
once per completed trade. It does not implement a separate commission parameter.
For new markets the historical aggregate round-trip fee is represented by the
supported `spread` input; both slippage sides are combined into its supported
`slippage` input. This conserves the historical nominal round-trip friction.
It does not claim to replicate a broker's bid/ask microstructure or measured fills.

These are documented historical simulation assumptions (source priority 3), not
marketing minima or newly estimated typical execution costs. No external broker
quote was necessary to establish this explicitly scoped assumption. No strategy
results are used to select or adjust costs. A source's additional leverage,
minimum ATR and other trading settings are **not** imported.

| Market | Pip size | Spread input | Slippage input | Total price friction/trade |
|---|---:|---:|---:|---:|
| EURUSD | 0.0001 | 0.00008 | 0.00002 | 0.00010 |
| GBPUSD | 0.0001 | 0.00010 | 0.00006 | 0.00016 |
| NZDUSD | 0.0001 | 0.00020 | 0.00010 | 0.00030 |
| USDCAD | 0.0001 | 0.00015 | 0.00010 | 0.00025 |
| USDCHF | 0.0001 | 0.00015 | 0.00010 | 0.00025 |
| USDJPY | 0.01 | 0.008 | 0.004 | 0.012 |
| XAUUSD | 0.01 | 0.30 | 0.10 | 0.40 |

Each market uses identical absolute costs for M15/H1/H4; frequency naturally
changes total friction. EURUSD retains its existing V1.8 assumption rather than
changing H1 or imposing the different historical per-side convention upon it.
Its original H1 jobs and profiles remain untouched. XAUUSD uses its own quoted
price scale; no FX value is copied to gold. No fictitious commission field is sent
to the evaluator.

`PRODUCTION_EXECUTION_V1` was frozen and hashed before any production canary.
Independent Decimal conversion checks reject x10/x100 errors. On the first 2048
Development bars for all 20 combinations, a fixed RSI rule in both directions
verifies exact per-trade cost deductions, identical entry/exit decisions, finite
metrics and Python/Numba agreement. Zero-cost comparisons are technical known-answer
checks only; they do not generate alternatives or consult Validation/OOS.

## Plan and execution

The 60 remaining jobs use 250,000 evaluations each. The three completed EURUSD H1
jobs from Production 01 are excluded by the operational plan. The matrix config
also omits an EURUSD_H1 execution profile so the frozen generic factory cannot
accidentally launch a new EURUSD H1 run from this matrix.

Run the operational launcher, which implements the exclusions and canary order:

```bash
python scripts/operations/production_02_run.py
```

Do not launch the generic matrix directly. Per-job configs are frozen before
execution. The launcher runs EURUSD M15/H4 seed1301 and six other markets' H1
seed1301 canaries first. These are final jobs, skipped when already COMPLETE.
After the canaries, the remaining jobs follow market, timeframe and seed order.
One child process runs at a time; process isolation releases memory between jobs.
This changes neither strategy generation nor evaluator semantics. The existing
cooperative 20-GiB memory guard checkpoints cleanly if reached. No runtime cap or
performance tuning changes are imposed.

Each completed job verifies 250K canonical identities/checkpoint consistency,
source/validation SQLite integrity, Development-only provenance, unchanged
policy/cost inputs, finite metrics where mathematically expected, survivor-only
OOS and exact promotion observations. Unknown infrastructure/integrity failures
stop the controller; identified dataset/profile failures isolate their combination.
No minimum survivor count is required. Restarting the launcher skips verified
COMPLETE jobs and resumes compatible interrupted checkpoints.

The library remains one row per canonical trading identity. Policy and execution
profile version are provenance, not new identity fields. Each job's immutable
config contains the version and manifest SHA, reachable from library observations.
Cross-market and cross-timeframe identities remain distinct as in V1.8.

## Reporting and interpretation

`runs/reports/production_02` stores the frozen input audit, plan, cost checks,
canaries, heartbeat and final reports. Per-job artifacts reside under
`runs/production/PRODUCTION_02`. Peak RSS is the child process OS high-water mark.
Report family/direction/predicate-count and survival distributions descriptively;
never use them to change this batch. TRUE OOS refers to isolation within each job,
not a claim that these calendar years have never appeared in earlier research.

Large datasets, SQLite and checkpoints remain local. Final publication includes
inputs, rationale, manifests and reports only. Existing tags are not moved. This
launch ends at Strategy Library accumulation; Portfolio Factory is not started.
