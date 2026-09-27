# General vs PROP_V1 A/B experiment

Freeze a General baseline and a PROP_V1 campaign with equal downstream data, EconomicSpec, Exact 5D Evaluator, FTMO profile, episode partitions, and portfolio-construction budget. Do not compare different evaluators or different validation windows.

Compare individual and portfolio distributions for trade frequency, active-day coverage, holding duration, independent timing, behavioral correlation, risk utilization, P95/P99 5D equity, Verification coverage, Challenge coverage, and breach behavior.

Primary reported deltas are vectors, not a pass threshold: `ΔP95_5D`, `ΔP99_5D`, target ladder deltas, independent signal density, duration, risk utilization, Verification coverage, and Challenge coverage. Validation is opened only after campaign freeze; OOS is separate.

