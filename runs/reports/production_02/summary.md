# SQX_ENGINE — PRODUCTION 02 FINAL OPERATIONAL AUDIT

**No ProductionJob was executed during this closure.**

## TOTAL PRODUCTION CAMPAIGN

- Production 01 jobs: **3**; Production 02 jobs: **60**; total jobs: **63**
- Total strategies evaluated: **15,750,000**
- Total OOS observations: **12,466**
- Total unique production strategies: **11,986**; legacy strategies: **299**; Strategy Library total: **12,289**
- Markets: **7**; timeframes: **M15, H1, H4**; market × TF: **21**; seeds per combination: **3**
- Batch integrity: **PASS**; Library integrity: **PASS**; Golden regression: **PASS**

## 21 MARKET × TIMEFRAME COMPARISON

|Market|TF|Source|Generated|Dev|Val|OOS|New unique|Rediscoveries|Runtime s|Strategies/s|Peak RSS MiB|Dev→Val|Val→OOS|Dev→OOS|Gen→OOS|
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|EURUSD|M15|PRODUCTION_02|750,000|1,244|251|86|84|2|1942.65|386.07|4171.6|0.2018|0.3426|0.0691|0.000115|
|EURUSD|H1|PRODUCTION_01|750,000|4,618|2,036|652|649|3|1467.89|510.94|3584.1|0.4409|0.3202|0.1412|0.000869|
|EURUSD|H4|PRODUCTION_02|750,000|5,063|2,191|734|726|8|1923.88|389.84|1677.8|0.4327|0.3350|0.1450|0.000979|
|GBPUSD|M15|PRODUCTION_02|750,000|1,484|290|129|127|2|2227.49|336.70|11931.8|0.1954|0.4448|0.0869|0.000172|
|GBPUSD|H1|PRODUCTION_02|750,000|4,648|964|212|212|0|1712.87|437.86|3461.0|0.2074|0.2199|0.0456|0.000283|
|GBPUSD|H4|PRODUCTION_02|750,000|6,448|1,169|498|481|17|2322.63|322.91|1597.3|0.1813|0.4260|0.0772|0.000664|
|NZDUSD|M15|PRODUCTION_02|750,000|29|0|0|0|0|1757.32|426.79|747.7|0.0000|0.0000|0.0000|0.000000|
|NZDUSD|H1|PRODUCTION_02|750,000|340|43|3|3|0|1006.50|745.16|641.1|0.1265|0.0698|0.0088|0.000004|
|NZDUSD|H4|PRODUCTION_02|750,000|5,418|2,030|118|118|0|1639.96|457.33|1690.4|0.3747|0.0581|0.0218|0.000157|
|USDCAD|M15|PRODUCTION_02|750,000|41|8|1|1|0|1664.88|450.48|685.4|0.1951|0.1250|0.0244|0.000001|
|USDCAD|H1|PRODUCTION_02|750,000|1,091|260|44|44|0|1077.93|695.78|1982.1|0.2383|0.1692|0.0403|0.000059|
|USDCAD|H4|PRODUCTION_02|750,000|6,494|1,000|241|240|1|1895.15|395.75|1631.7|0.1540|0.2410|0.0371|0.000321|
|USDCHF|M15|PRODUCTION_02|750,000|25|0|0|0|0|1677.59|447.07|712.3|0.0000|0.0000|0.0000|0.000000|
|USDCHF|H1|PRODUCTION_02|750,000|663|83|8|8|0|1023.80|732.57|1248.8|0.1252|0.0964|0.0121|0.000011|
|USDCHF|H4|PRODUCTION_02|750,000|7,122|1,460|594|562|32|2170.18|345.59|1828.6|0.2050|0.4068|0.0834|0.000792|
|USDJPY|M15|PRODUCTION_02|750,000|1,044|417|165|152|13|1787.28|419.63|4473.3|0.3994|0.3957|0.1580|0.000220|
|USDJPY|H1|PRODUCTION_02|750,000|4,177|2,167|1,069|1,032|37|1673.89|448.06|3519.6|0.5188|0.4933|0.2559|0.001425|
|USDJPY|H4|PRODUCTION_02|750,000|5,472|2,716|1,672|1,622|50|1946.09|385.39|1652.6|0.4963|0.6156|0.3056|0.002229|
|XAUUSD|M15|PRODUCTION_02|750,000|230|55|27|27|0|1577.24|475.51|1150.1|0.2391|0.4909|0.1174|0.000036|
|XAUUSD|H1|PRODUCTION_02|750,000|4,869|1,715|1,366|1,340|26|1924.64|389.68|3551.7|0.3522|0.7965|0.2806|0.001821|
|XAUUSD|H4|PRODUCTION_02|750,000|8,024|4,919|4,847|4,558|289|3033.66|247.23|2034.8|0.6130|0.9854|0.6041|0.006463|

## PRODUCTION 02 GLOBAL

Generated **15,000,000**; Development **63,926**; Validation **21,738**; OOS **11,814**; New unique **11,337**; rediscoveries **477**; runtime **10.00 h**; **416.83 strategies/s**; peak RSS **11931.8 MiB**.

## INTEGRITY

- jobs.sqlite: **60/60 COMPLETE**, exact plan ID match
- Discovery: **60/60** DB integrity PASS; Validation: **60/60** DB integrity PASS
- Operational integrity, promotion, provenance, checkpoint and dedup: **60/60 PASS**
- Strategy Library: SQLite integrity PASS; canonical_hash primary key PASS; total **12,289**
- V1.7 golden benchmark unchanged; V1.8 semantics, temporal policy and frozen execution profile manifest unchanged

## DISTRIBUTIONS

Library distributions are in `summary.json`: market, timeframe, market × timeframe, family, direction, predicate count, seed, policy and execution-profile version. Per-job family/direction/predicate telemetry and artifact evidence are retained there.

## FINAL STATUS

**PRODUCTION_02 COMPLETE** — Strategy Library ready for accumulation. No blockers.
