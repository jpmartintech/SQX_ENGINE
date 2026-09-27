# Portfolio Factory handoff

The Prop Factory emits a manifest and references; Portfolio Factory consumes them and does not reconstruct strategy semantics.

Required handoff artifacts:

- `prop_ready_manifest.json/parquet`;
- immutable StrategyDefinition/EconomicSpec references;
- R-normalized trade ledger reference and hash;
- ExecutionProfile and cost-status references;
- short-horizon metric vector;
- behavioral/timing descriptors;
- marginal utility vector and reference-set hash;
- data, generation, validation, and campaign provenance.

Portfolio Factory owns membership, weights, risk, max-open-risk, admission, FTMO simulation, diversity, and candidate persistence. Challenge and Verification may select different portfolios from the same Prop pool. MQL5/MT5 remains required for finalists.

