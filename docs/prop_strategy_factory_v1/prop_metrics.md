# PROP_V1 metric catalog

All metrics are stored as vectors with provenance, window count, split, market, timeframe, direction, and cost scenario. No single score replaces the vector.

## Window metrics

For horizons 1D, 2D, 3D, 5D, 10D, and 20D store trade count, net R, positive R, negative R, positive-window fraction, negative-window fraction, P50/P75/P90/P95/P99 net R, maximum favorable contribution, maximum adverse contribution, active-day fraction, and right-censoring state.

## Frequency

Store signals/day, signals/5D, active days/5D, median and P90 inter-signal duration, and fractions of windows with 0, 1+, 2+, 3+, and 5+ trades. Frequency has no positive value without edge, downside, and admission-capacity measurements.

## Duration and timing

Store median/P75/P90 holding duration, fraction closed within 1D/3D/5D, entry-hour distribution, market/timeframe distribution, overlap rate, and concurrent-position rate.

## Downside and robustness

Store expectancy, PF, negative-R quantiles, maximum drawdown, consecutive losses, loss-cluster length, daily-loss contribution, cost sensitivity, and Development/Validation stability. All rejection decisions carry reason codes.

## 5D_OPPORTUNITY_CONTRIBUTION vector

`{frequency, active_day_coverage, upper_tail_P75/P90/P95/P99, positive_window_fraction, downside_quantiles, independent_timing, risk_capacity_compatibility, holding_duration, cost_sensitivity, market_timeframe_direction}`.

The vector is evaluated standalone and when inserted into versioned reference pools. It is not a magic scalar and cannot bypass basic quality floors.

