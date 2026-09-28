# True Concurrent Portfolio Engine

Trade events are processed chronologically. Exits precede entries at identical timestamps. Each entry receives a fixed-fractional risk budget from equity known at entry. Floating PnL is marked from entry to current close and endpoint-scaled to evaluator R. Fees/slippage are already represented in evaluator R; funding is unavailable and not fabricated.
