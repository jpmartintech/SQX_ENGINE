# Portfolio risk semantics

The reconstructed pilot uses **PER_STRATEGY_RISK**: each strategy's net_R stream is scaled by the configured risk target, then combined with the historical portfolio weight. This means simultaneous active strategies can sum to more than the nominal single-strategy risk.

A distinct **PORTFOLIO_TOTAL_RISK** policy is represented by dividing the risk budget among active strategies (for example 0.5% each for two equal allocations inside a 1% total budget). It is not silently substituted into the pilot. No hidden second normalization is applied.
