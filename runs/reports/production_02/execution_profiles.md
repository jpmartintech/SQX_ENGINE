# PRODUCTION_EXECUTION_V1 — frozen assumptions

V1.8 deducts costs once per completed trade. No separate commission parameter exists. The spread field below represents the historical aggregate round-trip friction; it is not asserted to be a measured bid/ask spread. Slippage for new markets preserves both historical execution sides. EURUSD remains at its V1.8 baseline. No costs are scaled by timeframe.

| Market | TF | Spread | Slippage | Commission | Unit | Source | Status |
|---|---|---:|---:|---|---|---|---|
| EURUSD | M15 | 8e-05 | 2e-05 | no separate field | quote price/trade | V1.8 baseline | APPROVED |
| EURUSD | H1 | 8e-05 | 2e-05 | no separate field | quote price/trade | V1.8 baseline | APPROVED |
| EURUSD | H4 | 8e-05 | 2e-05 | no separate field | quote price/trade | V1.8 baseline | APPROVED |
| GBPUSD | M15 | 0.0001 | 6e-05 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| GBPUSD | H1 | 0.0001 | 6e-05 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| GBPUSD | H4 | 0.0001 | 6e-05 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| NZDUSD | M15 | 0.0002 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| NZDUSD | H1 | 0.0002 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| NZDUSD | H4 | 0.0002 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDCAD | M15 | 0.00015 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDCAD | H1 | 0.00015 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDCAD | H4 | 0.00015 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDCHF | M15 | 0.00015 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDCHF | H1 | 0.00015 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDCHF | H4 | 0.00015 | 0.0001 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDJPY | M15 | 0.008 | 0.004 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDJPY | H1 | 0.008 | 0.004 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| USDJPY | H4 | 0.008 | 0.004 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| XAUUSD | M15 | 0.3 | 0.1 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| XAUUSD | H1 | 0.3 | 0.1 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
| XAUUSD | H4 | 0.3 | 0.1 | no separate field | quote price/trade | historical sqx_lite profile | APPROVED |
