# Risk semantics

Legacy `risk_level=1.0` is a direct multiplier on the normalized portfolio return. It is neither 1% nor stop-loss risk and does not size a position.

V1.0 calibration exposes `risk_target` values 0.0025, 0.005, 0.0075 and 0.01. Because replay lacks stop distance, quantity, point value and causal stop-risk at entry, these are explicitly **account-return allocation targets relative to a 1% baseline**, with multiplier `risk_target / 0.01`. They must not be described as stop-risk sizing. A stop-risk model requires a replay extension carrying causal position units and monetary risk.
