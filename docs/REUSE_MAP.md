# SQX_ENGINE reuse map

| Component | Source | Decision | Reason |
|---|---|---|---|
| Data loading | `openclaw_quant_lab` concepts | Adapt | Preserve timestamp/OHLCV validation without importing project history. |
| Features | `openclaw_quant_lab` concepts | Adapt | Reuse causal indicator definitions in a small standalone feature engine. |
| Grammar/canonical hashing | OpenClaw strategy structures | Adapt | Independent serializable `StrategyDefinition` and canonical hash. |
| Reference backtester | OpenClaw execution semantics | Adapt | V1 implementation keeps next-bar execution and deterministic exits simple. |
| Fast evaluator | OpenClaw numerical ideas | Rewrite for P0 | Keep SQX_ENGINE dependencies and API independent. |
| Genetic search | OpenClaw architecture | Adapt interface | P0 keeps generation separate from evaluation; richer operators are later. |
| Quality funnel | `sqx_builder` concept | New | Product abstraction with explicit stages and persisted reasons. |
| Strategy store | New | Implement | SQLite fallback now, DuckDB/Parquet backend planned. |
| Portfolio builder | New | Implement | Actual strategy-return correlation and equal-weight selection. |
| `sqx_builder` source | Not present in workspace | No direct reuse | Only the requested simple architecture was used as inspiration. |

Historical experiment directories and Phase artifacts were deliberately not
copied into this repository.
