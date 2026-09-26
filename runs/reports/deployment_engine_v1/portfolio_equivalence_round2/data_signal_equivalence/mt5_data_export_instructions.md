# MT5 H1 data and predicate diagnostic export

The repository does not contain the exact H1 bars seen by the corrected FTMO
Strategy Tester run. `SQX_ExportH1Data.mq5` is a diagnostic script only; it
does not include trading or portfolio logic.

1. Copy `deployments/mql5/package/Scripts/SQX_ExportH1Data.mq5` to the MT5
   terminal `MQL5/Scripts/` directory and compile it in MetaEditor.
2. Run it in the same tester/terminal environment and symbol context, with
   `InpSymbol=EURUSD`, `InpTimeframe=PERIOD_H1`, `InpFrom=2023.11.01 00:00`,
   and `InpTo=2024.02.02 00:00`.
3. Copy `SQX_mt5_h1_export.csv` from the terminal's `MQL5/Files` (or the
   tester agent `Files`) directory into the Round 2D artifact directory as
   `mt5_h1_reference.csv`.

The raw timestamps must remain exactly as emitted by MT5. Do not convert them
before the alignment analysis. The export includes OHLC, tick volume, spread,
and real volume. Bid/Ask are not historical H1 fields in `MqlRates` and are
therefore not fabricated.

Predicate-level MT5 tracing is not available in the existing corrected EA.
After the raw-bar comparison, a separate optional diagnostic EA can be added
if the first divergence remains unresolved; this script is intentionally the
smallest evidence-gathering step.
