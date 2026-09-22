# Portfolio accounting

SQX_ENGINE V1.3 uses a deliberately simple equal-weight capital model.

For each selected strategy, the stored absolute equity curve is converted to
a normalized return curve:

```text
strategy_return[t] = equity[t] / equity[0] - 1
```

The portfolio return curve is the arithmetic mean of those normalized curves
using the configured equal weights. If a partial synthetic curve is shorter,
its terminal value is carried forward; production evaluations share the same
bar index and therefore do not need padding.

Portfolio metrics are then calculated from the combined curve:

* return: final combined return
* max drawdown: peak-to-trough decline of the combined return curve
* Sharpe: mean of bar-to-bar changes divided by their standard deviation,
  annualized with the existing V1 convention (`sqrt(252)`)

Strategy-return correlation continues to use actual strategy trade-return
vectors for the V1 portfolio selection constraint. Market returns are never
used as a proxy.
