# Minimum repository changes

Additive changes only:

```text
src/sqx_engine/prop_factory_v1/
  config.py              # versioned Prop config
  metrics.py             # rolling short-horizon vectors
  fitness.py             # objective adapter
  novelty.py             # economic/timing descriptors
  marginal_utility.py    # frozen reference-pool insertion
  promotion.py           # staged funnel and reason codes
  handoff.py             # EconomicSpec/PROP_READY manifest
configs/prop_strategy_factory_v1/
  prop_v1.json
  reference_portfolios.json
tests/prop_factory_v1/
docs/prop_strategy_factory_v1/
runs/reports/prop_strategy_factory_v1/
```

Reuse existing engine, evaluator, library, EconomicSpec, and exporter modules through adapters. Avoid refactoring stable General modules merely to anticipate future Crypto/Stocks/Futures lines.

