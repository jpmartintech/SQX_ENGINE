# PRODUCTION_01 — V1.8 frozen operational launch

Factory: `16a70ec0db6d58f8adb51ec8ae7caa361e139003` (`v1.8`). Grammar V1.7.
No engine, predicate, execution, funnel, gate, identity or resampling code changes.
The golden tag remains at `e7aae6b279ace1dba47ae395fad5156201acb2f1`.

## Inputs and data audit

Real M15 histories for all seven requested markets were found at
`/home/xaume/proyectos/sqx_lite/data`. The search also located copies in Windows
SQX data folders and monthly parquet shards. The complete local M15 CSV histories
were selected; test fixtures, analytics tables, incomplete downloads and monthly
shards were not production sources. No historical data were downloaded.

The operational script `scripts/operations/production_01_data.py` checks each
selected source's SHA, rows, dates, ordering, duplicate timestamps, NaN, OHLC
inequalities and timestamp spacing. Reports include every gap; weekend and holiday
closures are not fabricated as missing quotes. Original Date/Time labels and OHLCV
values are preserved in normalized CSV copies. Naive timestamps retain the V1.8
UTC bar-open convention; no timezone shift is inferred or applied.

H1 and H4 are derived directly from M15 through V1.8 `resample_closed`. Only complete
buckets are retained. The original golden EURUSD H1 stays byte-identical and is
selected for EURUSD H1 production; its M15-derived alternative is also audited and
retained. The updated catalog has seven native M15, one native golden H1, and
thirteen selected derived datasets (21 combinations). Every derived dataset has
source SHA and rule provenance. Large CSVs and databases remain outside Git.

## Temporal policy

`PRODUCTION_2016_2026_V1`, timestamps in UTC:

- Development: `[2016-01-01, 2022-01-01)`.
- Validation: `[2022-01-01, 2024-01-01)`.
- OOS: `[2024-01-01, latest available closed bar]`.
- Before 2016: `HISTORICAL_STRESS_RESERVED`, never evaluated in this launch.

Coverage preflight requires nonempty partitions, boundaries within seven calendar
days, and at least 80% of the weekday time grid. This operational data-coverage
check is fixed before production, not a trading gate. All selected datasets pass.

TRUE_OOS denotes isolation within each job: generation and selection see only
Development. These calendar years already occur in older research and benchmark
runs; this launch does not claim that they are globally never-inspected data.
No earlier OOS results are used to tune the frozen grammar or gates.

## Execution profiles and plan

The requested matrix contains 63 jobs, each with 250,000 unique evaluations.
Only EURUSD H1 has an accepted V1.8 production execution profile: spread 0.00008,
slippage 0.00002, initial capital 10000, unchanged price-unit semantics. No separate
commission is added to the frozen engine. The H4 profile was explicitly smoke-only.
External sqx_lite profiles express aggregated fee_pips and slippage_pips without
reliable spread/commission decomposition or broker/calibration provenance; they
are not silently translated into factory production costs.

Thus three jobs are READY (EURUSD H1 seeds 1301/1302/1303), and 60 are skipped as
MISSING_EXECUTION_PROFILE. This is 750,000 planned strategies, not 15.75 million.
The full plan is in `runs/reports/production_01/plan.json` and `plan.md`.

## Launch and resume

```bash
sqx production plan configs/production_01_ready.yaml
python scripts/operations/production_01_run.py
```

The operational launcher first runs/resumes seed1301 and verifies its complete
pipeline, checkpoint, SQLite integrity, temporal provenance, finite metrics
(except mathematically valid positive-infinite PF), promotion and deduplication.
Only CANARY_PASS permits the remaining READY jobs. The frozen scheduler runs
sequentially, skips COMPLETE jobs and resumes existing compatible checkpoints.
Data preparation and planning are pre-launch steps; do not rerun them while a batch is active, because catalog/config provenance is frozen.
Re-running this operational launcher is safe and does not regenerate complete jobs.
A failed job retains its error; healthy later jobs can continue via the scheduler.

Batch aliases and content-addressed IDs are persisted in `batch_identity.json`.
Each discovery config includes production_batch and production_policy; the library
stores its immutable path and SHA. Observations retain each rediscovery's job,
source run, validation run, metrics and provenance, even if canonical trading
identity already exists. Policy is not part of canonical trading identity.

## Evidence and boundaries

Preflight: 87 tests PASS (four existing fork deprecation warnings), FAST PASS,
AUDIT PASS, clean initial worktree and exact expected tags. Runtime artifacts,
per-job logs and summaries live under `runs/production/PRODUCTION_01`.
Final operational reports are under `runs/reports/production_01`.

The simple existing portfolio diagnostic runs unchanged as part of frozen V1.8.
No Portfolio Factory, weight optimization, gate tuning or follow-on phase is run.
