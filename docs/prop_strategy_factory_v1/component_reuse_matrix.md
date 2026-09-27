# Component reuse matrix

| Component | Decision | Boundary |
|---|---|---|
| Genetic engine infrastructure | REUSE_WITH_PROP_ADAPTER | New objective adapter; generic mutation/crossover unchanged |
| StrategyDefinition and canonical hashing | REUSE_UNCHANGED | Existing identity semantics remain authoritative |
| Causal data loading | REUSE_UNCHANGED | Same timestamp and lookahead controls |
| Feature/indicator engine | REUSE_WITH_PROP_ADAPTER | Only approved short-horizon features |
| Reference evaluator | REUSE_UNCHANGED | Prop metrics consume its causal ledger |
| Numba fast evaluator | REUSE_WITH_PROP_ADAPTER | Add metric extraction, not new trading semantics |
| Temporal split/isolation | REUSE_UNCHANGED | Prop windows are split-safe |
| Quality funnel | REUSE_WITH_PROP_ADAPTER | Add Prop reason codes and vector metrics |
| Strategy Library persistence | REUSE_WITH_PROP_ADAPTER | Add lineage namespace and Prop metadata |
| EconomicSpec / R normalization | REUSE_UNCHANGED | Automatic at promotion |
| ExecutionProfile | REUSE_UNCHANGED | Existing 21 profiles; unresolved costs remain explicit |
| Behavioral clustering | REUSE_WITH_PROP_ADAPTER | Timing/drawdown overlap descriptors |
| Reproducibility manifests | REUSE_UNCHANGED | Add Prop versions and reference-set hash |
| Checkpoint/resume | REUSE_UNCHANGED | Campaign seed and stage checkpoints |
| MQL5 exporter | REUSE_WITH_PROP_ADAPTER | Only semantics already supported by exporter |
| Prop short-horizon metrics | PROP_NEW | Rolling 1/2/3/5/10/20-day vectors |
| Marginal portfolio utility | PROP_NEW | Bounded reference-pool insertion tests |
| Prop grammar/exit configuration | CLONE_AND_SPECIALIZE | Versioned, additive configuration |
| Payout mode | NOT_REQUIRED | Future phase |

