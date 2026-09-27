# Phase A implementation contract

Phase A persists short-horizon metrics as versioned sidecars and does not mutate Strategy Library rows. Existing records without sidecar lineage resolve to `GENERAL`; `PROP_V1` is available through the synthetic/future metadata contract only.

Windows are calendar-day intervals anchored at Europe/Paris local midnight and are required to be fully contained in a split. The current validation implementation uses deterministic 60/20/20 Development/Validation/OOS boundaries over the ledger's local-date span. A 5D net-R value is normalized strategy economics; it is not an account return and contains no implicit 1R=1% conversion.

The recomputation command is:

```text
python scripts/prop_metrics_phase_a.py --sample 200
python scripts/prop_metrics_phase_a.py --strategy-id <canonical-strategy-id>
```

Outputs are stored under `runs/reports/prop_strategy_factory_v1_phase_a/`. The canonical StrategyDefinition remains the identity source; lineage and metrics are sidecar metadata keyed by strategy ID and version.

