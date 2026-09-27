# Phase B fitness adapter

Phase B adds a sidecar-only PROP fitness adapter. `evaluate_cheap` and
`evaluate_full` consume Phase A metric rows; neither invokes portfolio
simulation or Exact Equity Replay. The raw multiobjective vector is
authoritative and the optional compatibility scalar is the mean of available
min-max-normalized objectives, with objective directions recorded in
`fitness_objectives.json` and deterministic strategy-ID tie-breaking.

Development rows are the default selection input. Validation and OOS rows can
be requested explicitly for reporting, but the Phase B characterization never
uses them for selection. Missing values remain null with an explicit status;
they are not converted to zero. Phase A does not persist gross positive and
negative R totals, so profit factor is unavailable unless the optional
aggregate from the authoritative certified trade ledger is supplied; it is
never approximated. Portfolio target probability is deliberately outside this
adapter.

The public interface is in `sqx_engine.prop_factory_v1.fitness`:

```python
evaluate_cheap(candidate_statistics)
evaluate_full(metrics, costs)
dominates(a, b)
pareto_rank(frame)
fitness_vector(frame, strategy_id)
```
