# PROP_EXIT_GRAMMAR_V1 design

| Exit family | Initial treatment | Rationale / risk |
|---|---|---|
| ATR stop/target geometry | KEEP and parameterize in Prop config | Existing EconomicSpec and parity path |
| Shorter bar-count time exit | ADD candidate | Directly targets 5D opportunity; causal and exporter-compatible if supported |
| Intraday/session exit | DESIGN_ONLY | Potential frequency benefit; timezone and MQL5 parity risk |
| Break-even | DESIGN_ONLY | Requires causal state semantics and dedicated parity tests |
| Trailing exit | DESIGN_ONLY | Higher implementation and path-dependence risk |
| Session-aware stop/target | DESIGN_ONLY | Requires execution-profile/session provenance |

No exit family is promoted without exact evaluator, cost, and MQL5 parity tests. Exit changes are evaluated as strategy semantics, not as portfolio leverage.

