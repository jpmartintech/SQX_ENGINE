# SQX Strategy Factory — V1.8 production baseline

**Strategy Factory ≠ Portfolio Factory.**

> Strategy Factory produces many individually validated, reproducible and traceable strategies. Portfolio construction and aggressive return optimization are separate downstream concerns.

V1.8 freezes V1.7 trading semantics. Predicates, canonical definitions, numeric
execution, next-bar entry, ATR SL/TP, time exits, fitness, quality funnel and
Validation/OOS gates are unchanged. The old portfolio remains a diagnostic and a
regression artifact. Library promotion includes all verified OOS survivors, not
only the diversified subset or the ten diagnostic portfolio members.

## Dataset catalog

```bash
sqx data scan
sqx data list
```

`data/catalog.json` is the central registry. It records market, timeframe, path,
native/derived origin, source timeframe and SHA, rows, columns, dates, duplicates,
NaNs, chronology and one of `DATASET_AVAILABLE`, `DATASET_MISSING`,
`DATASET_INVALID`. A derived dataset has `kind: derived` and explicit provenance.

Supported initial dimensions are EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY,
XAUUSD, with M15/H1/H4. Native files are resolved centrally from `data/cloud`,
using market plus timeframe aliases, e.g. `EURUSD_1H.csv`, `GBPUSD_M15.csv`.
Conflicting native files are invalid rather than chosen arbitrarily. Missing
markets are not synthesized. SHA and provenance are checked again before each job.

The declared timestamp convention is **UTC bar open**. Native bars must be
aligned to their declared interval, nonoverlapping and fully closed at scan time.
Unclosed/future native bars are invalid. Historical H1 loading and timestamp
semantics are preserved. A derived bar at t becomes available only at t+duration;
its `available_at` column records that time. The evaluator still enters on the
following bar.

Resampling uses open=first, high=max, low=min, close=last, volume=sum. Only exact,
contiguous, complete source grids are emitted; leading/trailing partial groups,
session gaps and future groups are omitted. No filling, interpolation or
upsampling is performed. H4 is anchored to UTC multiples of four hours. Derived
CSVs live under `data/derived`, with source hash and row count in their names.
Their contents are verified against recomputed derivation during scans, and
source/output SHA chains are verified during resolution. Raw datasets and derived
CSVs are excluded from Git; catalog metadata is committed.

Available at release: EURUSD H1 native (143,197 rows), EURUSD H4 derived (35,651
complete rows); 19 other market/timeframe combinations are missing.

## Planning and execution

```bash
sqx production plan configs/production_v18_matrix.yaml
sqx production run configs/production_v18_smoke.yaml
sqx production status
sqx production resume configs/production_v18_smoke.yaml
sqx factory status
```

The matrix template expands 7 markets × 3 timeframes × 3 seeds = 63 jobs. With the
release catalog, six are ready and 57 are `SKIPPED_DATA_MISSING`. This template is
**prepared only**; its 250K jobs were not launched. The smoke uses one seed and 1K
per available combination: two completed jobs and 19 missing-data skips.

A `ProductionJob` has a content-derived identity incorporating market, timeframe,
seed, evaluations, grammar, dataset provenance and effective configuration.
Output paths and per-attempt resource limits do not determine trading identity.
Duplicate matrix axes are rejected. States are PENDING, RUNNING, COMPLETE, FAILED,
INTERRUPTED, plus explicit skipped-data states. Missing/invalid data or a failing
job do not prevent other independent jobs from being processed.

Jobs are persisted in `runs/production/jobs.sqlite`. A many-to-many `batch_jobs`
index lets overlapping batches share a completed job without losing batch
membership or executing it twice. A per-job advisory file lock prevents concurrent
producers from executing the same job. The default scheduler is sequential;
`workers` controls the existing evaluator path and defaults to one.

Artifacts are organized as:

```text
runs/production/<market>/<timeframe>/seed_<seed>/<job-id-prefix>/
    job.json
    dataset.json
    discovery.yaml
    discovery.sqlite
    checkpoint.json
    discovery_summary.json
    production.log
    validation.yaml
    validation.sqlite
    validation_summary.json
    final_candidates.csv
    promotion.json
```

Job records include attempt count, timestamps, status/error, generated count,
Development candidates, Validation/OOS counts, promoted eligibility and cumulative
runtime. `promoted` counts eligible observations: the promotion report separately
records new inserts and exact duplicates. Batch summaries and CLI status preserve
both successful and skipped/failed work.

## Interruption, resume and resource guards

Ctrl+C is cooperative. Genetic checkpoints retain RNG, population, canonical
hashes, counters, family telemetry and dataset/config context. A stopped funnel
rolls back its partial transaction and checkpoints the completed discovery;
resume repeats the deterministic funnel, **not Genetic**. Tests verify that its
rows/counters match an uninterrupted run.

Validation results are committed transactionally. A resume finds an already
committed validation run and recovers its JSON/CSV exports without evaluating OOS
again. Promotion is transactional and idempotent; an interrupted import can be
retried without duplicating identities or observations. COMPLETE jobs are skipped.
Resume uses the stored batch plan and rejects changed data/configuration instead
of silently starting a different job. A discovery database without a checkpoint
is rejected rather than silently restarted (for example after an early hard kill).

Optional batch settings:

```yaml
resource_guards:
  max_memory_gb: 8
  max_runtime: 3600  # seconds per attempt
```

Discovery checks guards between strategy evaluations, funnel/diversity check at
strategy boundaries, and orchestration checks between pipeline phases. A guard
creates an INTERRUPTED state and clean checkpoint where discovery has begun.
These are **cooperative soft guards**, not OS memory caps: one compiled operation
or an atomic phase may overshoot before reaching the next safe boundary. There
is no forced process kill. Limits can be raised before resume without changing
job identity or checkpoint configuration.

Periodic discovery heartbeats record strategies/sec, RSS, elapsed time, ETA,
duplicates and current Basic candidate count in `production.log`.

## Temporal policy

The compatibility default remains the exact V1.7 chronological 70/15/15 split and
its original rounding. Full-data features are never passed to discovery. The
explicit alternative is illustrated in
`configs/production_v18_explicit_dates_example.yaml`; it was not selected as a
new production horizon and was not run on production data.

```yaml
temporal_policy:
  mode: explicit_dates
  development: {start: '2016-01-01', end: '2021-12-31'}
  validation: {start: '2022-01-01', end: '2023-12-31'}
  oos: {start: '2024-01-01', end: latest}
```

Ranges must be ordered, disjoint and nonempty. Date-only ends include that entire
UTC day; timestamp ends are exclusive. `latest` is only allowed as OOS end and is
bound to the dataset SHA and actual split manifest. Explicit policies may exclude
older rows or leave gaps. Selection uses bar-open timestamps. Both discovery and
validation use the same partition implementation and verify identical provenance.
No definitive new horizon has been chosen.

## Timeframe and execution assumptions

Indicator lookbacks, ATR periods and time exits remain in **bars**, without
implicit timeframe scaling. For example, time exits 24–96 correspond nominally to
6–24 hours on M15, 24–96 on H1 and 96–384 on H4, before session gaps. ATR(14) spans
14 bars on every timeframe. This is infrastructure reuse, not a redesigned grammar.

Every available market/timeframe requires an explicit `execution_profiles` entry
with finite, nonnegative spread/slippage in native **price units**, not pips or
lots. No costs are inferred for GBPUSD, metals or JPY. Missing costs fail planning.
The smoke explicitly reuses the existing EURUSD fixed-price cost model for H1/H4:
spread 0.00008, slippage 0.00002, initial capital 10000. H4 carries a provenance note
that this is the existing instrument model reused for infrastructure testing,
not a new empirical timeframe calibration. No OOS tuning occurred.

Validation and OOS retain 20 minimum trades, PF ≥ 1, expectancy ≥ 0, Sharpe ≥ 0.
Production refuses modified gate configs. No feedback from either phase reaches
mutation, crossover, ranking, fitness or generation. Family telemetry remains
measurement only. New scientific searches, grammar improvements and portfolio
optimization are outside this release.
