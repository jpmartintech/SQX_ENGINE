# Strategy Library contract

Use the existing library with explicit lineage rather than migrating historical records. Existing entries remain `GENERAL`; new records carry `PROP_V1` lineage and cannot collide with existing canonical identities.

Required Prop record fields:

`strategy_id`, `canonical_hash`, `factory_lineage`, `factory_version`, `grammar_version`, `fitness_version`, `economic_spec_version`, `campaign_id`, `StrategyDefinition`, `EconomicSpec`, R-ledger reference, ExecutionProfile, data provenance, generation metadata, validation metadata, behavioral metadata, short-horizon metric vector, marginal-utility metadata, and `PROP_READY` status/reason.

The library handoff is immutable by campaign. Re-running a campaign with the same inputs must produce the same IDs, metrics, and manifest hash.

