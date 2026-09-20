# SQX_ENGINE

Standalone practical strategy-generation engine. The first vertical slice
supports EURUSD H1 data, portable strategy definitions, causal evaluation,
random generation, a basic quality funnel, persistent storage and simple
portfolio construction.

## Run

```bash
PYTHONPATH=src python -m sqx_engine.cli run configs/eurusd_h1.yaml
```

The configured V1 flow is:

```text
data → features → generator → fast backtest → basic filter
     → SQLite strategy store → correlation-aware portfolio → report
```

The storage abstraction is designed for DuckDB/Parquet, but uses SQLite in
the current environment because DuckDB is not installed. The later funnel
stages are represented and persisted as configurable stages; their full
robustness implementations are planned after the P0 end-to-end milestone.

The 100-strategy acceptance run is an engineering test, not evidence of a
trading edge. The current P0 run uses the Random generator; the generator
interface and a minimal Genetic-compatible façade are available for the next
milestone.

See [docs/REUSE_MAP.md](docs/REUSE_MAP.md) for reuse decisions.
