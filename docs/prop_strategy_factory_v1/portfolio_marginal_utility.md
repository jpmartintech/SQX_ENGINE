# Bounded marginal portfolio utility

Maintain a versioned, immutable reference set containing market-, timeframe-, direction-, frequency-, and behavioral-diverse portfolios. The set is frozen per campaign.

For a candidate S, insert S into representative pools and compute deltas in:

- 5D target-distance and upper-tail distributions;
- active-day and independent-signal coverage;
- risk utilization and cap competition;
- downside, loss clustering, and drawdown overlap;
- holding-duration and cost sensitivity.

Use a small deterministic sample in generation, then exact/cached replay for survivors. The result is `MARGINAL_PORTFOLIO_UTILITY_V1` with raw before/after metrics, reference-set hash, candidate hash, and reason codes. It is a promotion signal, never a replacement for standalone quality or causal validation.

