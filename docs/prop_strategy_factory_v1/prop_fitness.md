# PROP_V1 fitness and search

## Staged funnel

1. **Cheap generation fitness**: expectancy, PF, trade count, active-day coverage, 5D positive-window fraction, 5D upper-tail R, negative-tail R, holding duration, and loss clustering.
2. **Fast causal backtest**: complete trade ledger, geometry, costs, and split-safe rolling metrics.
3. **Short-horizon quality**: 1/2/3/5/10/20-day vector, target-distance metrics, frequency, duration, and downside.
4. **Novelty/independence**: signal timing, R-series, drawdown, and behavioral redundancy.
5. **Bounded marginal utility**: insertion into fixed reference portfolios; exact replay only for the bounded survivor set.
6. **Robustness**: cost scenarios, temporal stability, negative controls, and final PROP_READY contract.

The inner genetic loop never runs Exact Equity Replay. Pareto rank is preferred. If a scalar is required by existing infrastructure, use documented normalized ranks with raw objectives persisted; no cumulative-R-only fitness is permitted.

## Objective directions

Maximize edge, usable 5D positive tail, independent timing, active-day coverage, and positive risk-capacity contribution. Minimize negative tail, loss clustering, redundancy, excessive duration, and cost sensitivity. Challenge and Verification objective adapters are separate downstream consumers; the factory initially produces one high-quality pool.

