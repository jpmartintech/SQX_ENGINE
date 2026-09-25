# Economic model

`RawStrategyReturn → AccountEquityEngine → economic PnL → FtmoSimulator`.

For account capital `C`, normalized stream `r_t`, and configured allocation target `q`:

```text
multiplier = q / 0.01
pnl_t = r_t × C × multiplier
equity_t = C + Σ pnl_t
```

Weights are applied once before this conversion. There is no second portfolio-size division and no arbitrary constant. FTMO receives USD PnL and computes daily/total limits against the same account capital. The model is realized-only because replay does not contain reliable floating PnL.
