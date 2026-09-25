# Portfolio Factory data contract

A portfolio is downstream metadata over immutable strategies:

`portfolio_id, portfolio_hash, sorted strategy_ids, weights, risk config, constraints, realized-return stream, metrics, FTMO metrics, robustness metadata, provenance, created_at`.

The portfolio factory does not alter StrategyDefinition or Strategy Library rows.
