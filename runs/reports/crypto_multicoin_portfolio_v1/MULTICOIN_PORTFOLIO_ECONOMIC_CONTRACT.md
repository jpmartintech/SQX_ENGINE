# Multi-coin portfolio economic contract

One chronological shared equity curve spans all primary assets. Total intended heat is 1% of current portfolio equity, allocated by non-negative weights summing to one. Exits precede entries at equal timestamps. Floating PnL is marked at event and daily timestamps; realized PnL, fees and slippage are retained. Funding is not fabricated. Ruin is equity <= 0. Metrics are calculated from the combined stream, never averaged standalone metrics.
