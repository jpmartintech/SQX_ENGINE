# Strategy Library

The library is the output of the Strategy Factory. It supplies reproducible raw
material to a separate future Portfolio Factory; it does not optimize allocation,
leverage or portfolio returns.

## Commands

```bash
sqx library stats
sqx library list --market EURUSD --timeframe H1
sqx library list --family Trend+Volatility+Structure --limit 20
sqx library import-v17
```

The default location is `library/strategies.sqlite`; `--db` selects another
library. Listing supports combined market/timeframe/family filters. Queries use
only the library, without opening discovery databases. Runtime SQLite files are
not uploaded to Git; `library/manifest.json` and reports preserve release metadata.

## Identity and promotion

`canonical_hash` is the primary key. Existing V1.7 canonical representations already
include market, timeframe, grammar version, direction, predicates, logic, ATR,
SL/TP and time exit; they are unchanged. Thus identical rules on EURUSD H1,
GBPUSD H1 and EURUSD M15 have distinct identities.

Default progression is:

```text
GENERATED → DEVELOPMENT_PASS → VALIDATION_PASS → OOS_PASS → LIBRARY
```

Default promotion requires a completed, single-owner discovery run, matching
source/config/dataset fingerprints, Development-only provenance, matching split
manifests, TRUE_OOS labeling, frozen gates, canonical definitions and passing
Validation/OOS evidence. Orphans, retrospective runs, config mismatches and failed
prior gates are rejected. All eligible OOS survivors are promoted, regardless of
whether they enter the diagnostic portfolio.

`promotion_policy` may explicitly request GENERATED, DEVELOPMENT_PASS or
VALIDATION_PASS for analysis. Such rows carry their lower level and are excluded
from default `stats`/`list`; use `--include-analysis` to see them. Later OOS evidence
can upgrade an identity without inserting another copy.

## Schema and provenance

- `strategies`: one canonical identity, with explicit market/timeframe,
  factory/grammar versions, seed/source/validation/job IDs, full canonical JSON,
  predicates, exits, family/count, all three date ranges and metric sets,
  dataset SHA, creation/last-seen timestamps, discovery count and artifact refs.
- `library_jobs`: immutable provenance for each producer/import job, including
  paths and fingerprints for the source DB, config and dataset, plus validation
  run ID, splits, seed and versions.
- `observations`: every distinct encounter, preserving its job/run/validation
  identity and complete evidence. Foreign keys prevent orphan observations.

The first promoted metrics remain the primary snapshot unless a higher promotion
level supersedes an analytical record. Subsequent metrics/provenance remain in
observations; nothing is silently replaced with the best later OOS result.
`discovery_count` counts distinct source runs. Repeating the same import is
idempotent, including its counters. Different jobs finding the same canonical
strategy retain their observations without duplicating the strategy.

Equity/PnL and trade artifacts are referenced when available; large curves are not
copied into the library. Current references point to source/validation databases,
which preserve metrics and canonical evidence; they do not pretend that a trade
ledger was persisted when the source run did not save one.

## V1.7 golden import

The importer reads the verified golden manifest and source databases read-only,
then records `LEGACY_V1_7_GOLDEN_IMPORT`. It imported exactly **299** TRUE OOS
survivors, with all Development/Validation/OOS metrics and original provenance.
Immediately afterward the empty library contained 299 identities. A second import
rejected 299 exact duplicates and added zero observations.

The two V1.8 smoke jobs then supplied six eligible observations: the two EURUSD H1
identities already existed, and four EURUSD H4 identities were new. Release totals:
**303 identities, 305 observations**, with EURUSD H1=299 and H4=4. The initial
import and dedup checks are retained separately under `runs/reports/v18`.

Promotion is a transaction. If interrupted, it rolls back; rerunning the same
completed job is safe. For operational backups use SQLite's backup API or a
consistent filesystem snapshot, not an incomplete copy of an active transaction.
Keep referenced run artifacts alongside backups so the full chain remains auditable:

```text
strategy → observation → job → source run → config → dataset SHA → factory/grammar
```
