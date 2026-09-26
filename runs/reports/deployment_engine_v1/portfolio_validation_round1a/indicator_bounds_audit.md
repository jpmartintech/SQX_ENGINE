# Indicator Bounds Audit

The common MQL5 runtime was audited for all V1.7 helper families used by the
20-strategy portfolio.

| Family | Required access | Protection | Short-history result |
|---|---:|---|---|
| SMA / Bollinger | `s .. s+n-1` | `SQX_RatesReady` | `EMPTY_VALUE` |
| EMA / EMA slope / EMA pair | `s .. s+4n`, including slope offset | `SQX_RatesReady` | `EMPTY_VALUE` |
| True range / ATR | `s .. s+n` | `SQX_RatesReady` and nested TR check | `EMPTY_VALUE` |
| ROC | `s+n` | `SQX_RatesReady` | `EMPTY_VALUE` |
| RSI | `s .. s+n` | `SQX_RatesReady` | `EMPTY_VALUE` |
| Williams %R | `s .. s+n-1` | `SQX_RatesReady` | `EMPTY_VALUE` |
| Breakout | `s+1 .. s+n` | `SQX_RatesReady` | `EMPTY_VALUE` |
| ATR regime | current ATR plus all baseline ATR windows | nested helper checks | `EMPTY_VALUE` |
| Compression | BB, EMA and ATR dependencies | dependency checks | `EMPTY_VALUE` |
| Fractals | `j .. j+2d` | pivot bounds check | `false` |
| HH/HL/LH/LL structure | bounded pivot scan | bounded start and pivot checks | `EMPTY_VALUE` |

`SQX_LoadRates` now checks the exact `CopyRates` count before setting series
indexing. Signal evaluation remains on `shift=1`; no lookahead was added.

Current portfolio counts are 600 for ordinary strategies, 803 for the first
200-period EMA strategy, and 808 for the 200-period EMA slope with horizon 6.
