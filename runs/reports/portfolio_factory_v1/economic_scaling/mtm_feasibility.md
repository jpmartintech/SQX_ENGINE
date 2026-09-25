# MTM feasibility

**Status: REQUIRES_REPLAY_EXTENSION.** Replay contains entry/exit timestamps, prices, direction and net trade PnL, and the original OHLC datasets are available. However, the current return stream is sparse at realized exits and does not preserve the open-position state/quantity and causal per-bar mark-to-market required for exact floating PnL. Implementing MTM would require replaying each strategy with position state and emitting a common-clock per-bar exposure/PnL stream. No MTM engine was added in this calibration.
