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

The storage abstraction is designed for DuckDB/Parquet, but uses SQLite in
the current environment because DuckDB is not installed. Monte Carlo,
negative controls, regime analysis and cross-market validation are deferred
to later milestones.

Historical backtest metrics are engineering outputs, not evidence of a
trading edge. The 1K factory run is a product/infrastructure milestone.

See [docs/REUSE_MAP.md](docs/REUSE_MAP.md) for reuse decisions.
