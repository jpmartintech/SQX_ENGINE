# Replay V2 / MTM extension design

The current replay emits realized exit events only. A future causal MTM replay must retain, per open position, timestamp, strategy ID, market, direction, entry price, quantity/exposure, current closed-bar price, floating PnL and realized PnL. The evaluator should emit a common-clock event after each closed bar, calculate floating PnL from that bar only, and preserve the frozen next-bar execution semantics. Portfolio aggregation can then compute daily equity including floating PnL without fabricating it in V1.0.
