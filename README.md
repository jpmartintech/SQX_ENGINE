# SQX_ENGINE

Standalone practical strategy-generation engine. V1.4 supports EURUSD H1
data, portable strategy definitions, causal array evaluation, Random and
Genetic generation, a staged quality funnel, persistent storage and simple
portfolio construction.

## Run

```bash
PYTHONPATH=src python -m sqx_engine.cli run configs/eurusd_h1.yaml
```

The configured V1 flow is:

```text
data → cached features → Genetic/Random → aggregate backtest → basic filter
     → stability → plateau → cost → execution → behavioral diversity
     → SQLite strategy store → correlation-aware portfolio → report
```

V1.3 added portable project-relative data paths, deterministic process workers
for independent evaluation batches, bounded evaluator caches, and resumable
checkpoints. The Genetic coordinator deliberately preserves the V1.2
`ask → evaluate → tell` order; workers do not change the evolutionary path.

V1.4 adds an optional Numba numerical core.  `engine: auto` (the default)
uses Numba when installed and falls back to the Python evaluator otherwise;
`--engine python` remains available as a correctness/debug oracle.  The
Numba path uses the same causal trade rules and is covered by reference and
Golden 1K equivalence checks.

Place the reference dataset at `data/cloud/EURUSD_1H.csv` (the local xauserver
checkout may use an ignored symlink) and run:

```bash
sqx run configs/eurusd_h1_smoke.yaml --workers 2
sqx run configs/eurusd_h1_250k.yaml --workers auto --engine numba --resume
```

The 250k configuration is prepared for a Ryzen benchmark but is not executed
as part of the V1.4 release on xauserver.

For a Ryzen benchmark after installing the release:

```bash
git checkout v1.4
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -q
time sqx run configs/eurusd_h1_1k.yaml --workers 1 --engine numba
time sqx run configs/eurusd_h1_1k.yaml --workers 2 --engine numba
```

The 250K configuration is prepared for the Ryzen machine only. It is not
executed on xauserver in this milestone.

## V1.5 scale mode

`generator.mode: legacy` remains the compatibility default. `mode: scale`
adds effective mutation, bounded novelty retries, duplicate telemetry and a
periodic `SQX HEARTBEAT`; it does not change backtest or funnel semantics.
Runtime counters distinguish `attempts`, `duplicates`, `unique` and
`backtested`. Checkpoints use flush/fsync plus atomic rename, and SIGINT writes
an `INTERRUPTED` resumable checkpoint.

Use `python scripts/audit_checkpoint.py PATH` for read-only checkpoint
forensics and `PYTHONPATH=src python scripts/benchmark_generator.py
--sizes 1000,10000,50000` for generator-only scale measurements. The 250K
config is scale mode but remains reserved for the Ryzen run after review; this
checkout does not contain the source dataset or the reported 115K checkpoint.

The storage abstraction is designed for DuckDB/Parquet, but uses SQLite in
the current environment because DuckDB is not installed. Monte Carlo,
negative controls, regime analysis and cross-market validation are deferred
to later milestones.

Historical backtest metrics are engineering outputs, not evidence of a
trading edge. The 1K factory run is a product/infrastructure milestone.

See [docs/REUSE_MAP.md](docs/REUSE_MAP.md) for reuse decisions.

## V1.6 Validation / OOS

Evaluate existing candidates without generating or changing strategies:

```bash
sqx validate configs/eurusd_h1_v16_validation.yaml
```

The historical 250K run is explicitly a retrospective split test because discovery
used the full dataset. The pipeline applies fixed Validation and OOS gates and
builds a portfolio only from final survivors. Future Development-only discovery is
configured in `configs/eurusd_h1_250k_clean_v16.yaml`.
See [V1.6 methodology and outputs](docs/V1.6_VALIDATION.md).


## V1.7 Grammar expansion

V1.7 adds Trend, Momentum, Volatility and causal Structure families with 1–4
predicates, versioned canonical hashing, family telemetry and numeric Numba
predicates. Development/Validation/OOS boundaries and gates remain unchanged.

```bash
python scripts/benchmark_grammar.py configs/eurusd_h1_grammar_v17_1k.yaml --output runs/reports/v17/1k.json
```

The benchmark command is capped at 50K. The clean 250K configuration is prepared
but was not run. See [grammar definitions, causality and compatibility](docs/V1.7_GRAMMAR.md).
Validation exports use `summary_path` / `csv_path`; conflicting legacy aliases
now fail before writing outputs.


## V1.8 Production Factory

```bash
sqx benchmark v1.7 --mode fast
sqx data scan
sqx production plan configs/production_v18_matrix.yaml
sqx production run configs/production_v18_smoke.yaml
sqx production status
sqx library stats
sqx factory status
```

V1.8 freezes V1.7 grammar and trading semantics, adds a dataset catalog with causal
resampling, resumable production jobs and an independently queryable Strategy
Library. The 250K matrix is prepared, not automatically executed.

- [Production operations and temporal/cost policies](docs/PRODUCTION_FACTORY.md)
- [Library, deduplication and provenance](docs/STRATEGY_LIBRARY.md)
- [Golden benchmark: FAST, AUDIT and FULL](docs/GOLDEN_BENCHMARK.md)

Strategy Factory produces validated strategies; Portfolio Factory is a separate
future project. No advanced portfolio optimization is included.
