# PROP Strategy Factory V1 — Generation Pilot

The pilot is an additive manufacturing line. It subclasses the existing
genetic generator and selects only already-implemented causal V1.7 predicate
families; it does not change General Factory behavior, canonical strategy
identity, or Strategy Library records.

`PROP_GRAMMAR_V1` is a bounded V1.7 subset: shorter existing EMA, slope,
breakout, ROC/Williams, structure and volatility configurations. No new
indicators, session predicates, or grammar semantics are introduced.

`PROP_EXIT_V1` samples the existing ATR stop/target geometry with
`stop_atr ∈ {1.0, 1.5, 2.0}`, `target_atr ∈ {1.0, 1.5, 2.0, 3.0}` and causal
bar-count exits `{4, 8, 12, 24}`. Trailing, break-even, session and
discretionary exits are out of scope.

Generation and cheap survivor selection use Development only. Validation is
opened only after the survivor set is frozen. OOS is not loaded or inspected.
The pilot survivor width is 30% and is calibration-only, not a production
approval rule.

Pilot records are PROP_V1 lineage records with `portfolio_useful` and Phase E
handoff pending. Phase D is required before any final PROP_READY state.
