# Phase C promotion funnel

Phase C evaluates strategies stage by stage in the fixed order
`GENERATED → CAUSAL → BASIC_EDGE → SHORT_HORIZON_QUALITY → COST_ROBUST →
TEMPORAL_STABLE → NOVEL → PORTFOLIO_USEFUL → PROP_READY`.

The policy is versioned separately from funnel logic and is explicitly
calibration-only in the current analysis profile. Every stage emits a status
and machine-readable reason codes. Existing GENERAL strategies can be
evaluated in analysis mode, but their lineage and library records are never
changed. `PORTFOLIO_USEFUL` is `PENDING_PHASE_D`, and final `PROP_READY` is
blocked on both Phase D utility and the Phase E handoff contract.

Phase D consumes `PortfolioMarginalUtilityResult`; Phase E consumes the
handoff schema persisted by the Phase C command. Pareto front membership is
diagnostic and is never used as an automatic promotion decision.
