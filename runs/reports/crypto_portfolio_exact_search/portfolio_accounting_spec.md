# Exact portfolio accounting

Events are processed chronologically. Exits precede entries at equal timestamps. A single 1% total risk budget is split by nonnegative weights. Floating PnL is marked at daily closed-bar marks and all event timestamps; endpoint scaling matches the frozen V3 replay contract. Ruin is equity <= 0.
