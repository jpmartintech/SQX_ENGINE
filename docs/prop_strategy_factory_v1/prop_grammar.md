# PROP_GRAMMAR_V1 design

## KEEP

Trend, Momentum, Volatility, and Structure predicate families; causal closed-bar evaluation; 1–4 predicate complexity; canonical StrategyDefinition and hashing.

## MODIFY

Use shorter parameter ranges only in a versioned Prop configuration. Add a complexity penalty, family-balance reporting, and explicit session/timeframe provenance. Preserve AND/OR semantics and lookahead protections.

## ADD — design candidates, not implementation commitments

- shorter EMA and momentum relationships;
- shorter breakouts and compression-release predicates;
- intraday structure/fractal state;
- causally supported session/time-of-day features.

Each addition requires an economic rationale, a causal test, an MQL5 parity plan, and ablation evidence. No indicator is added solely to increase search size.

## REMOVE

None at design time. Existing general grammar semantics and historical strategies remain unchanged.

