# SQX_ENGINE

Standalone practical strategy-generation engine. V1.3 supports EURUSD H1
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

V1.3 adds portable project-relative data paths, deterministic process workers
for independent evaluation batches, bounded evaluator caches, and resumable
checkpoints. The Genetic coordinator deliberately preserves the V1.2
`ask → evaluate → tell` order; workers do not change the evolutionary path.

Place the reference dataset at `data/cloud/EURUSD_1H.csv` (the local xauserver
checkout may use an ignored symlink) and run:

```bash
sqx run configs/eurusd_h1_smoke.yaml --workers 2
sqx run configs/eurusd_h1_250k.yaml --workers auto --resume
```

The 250k configuration is prepared for a Ryzen benchmark but is not executed
as part of the V1.3 release on xauserver.

The storage abstraction is designed for DuckDB/Parquet, but uses SQLite in
the current environment because DuckDB is not installed. Monte Carlo,
negative controls, regime analysis and cross-market validation are deferred
to later milestones.

Historical backtest metrics are engineering outputs, not evidence of a
trading edge. The 1K factory run is a product/infrastructure milestone.

See [docs/REUSE_MAP.md](docs/REUSE_MAP.md) for reuse decisions.
