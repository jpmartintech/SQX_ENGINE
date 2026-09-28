# SQX CRYPTO EXACT PORTFOLIO SEARCH — FINAL STATUS

Starting commit: `f7efcfe`  
Final commit: pending  
Protected V2 LOCKBOX access before/after: `0 / 0`

## Frozen library

Input: 63 strategies. Modified: 0. Strategy Factory and PRICE_ONLY grammar remained frozen.

## Exact evaluator

Reference/fast equivalence: 100/100 PASS; maximum absolute metric delta: 1.819e-12. The fast evaluator uses integer nanosecond timestamps, chronological exits-before-entries, same-timestamp self-exit realization, floating PnL, fixed total risk, and corrected V3 accounting.

Warm exact benchmark: 0.314729 seconds/portfolio; approximately 3.18 portfolios/second; estimated 75K runtime 23604.7 seconds.

## Search

Random exact: 50,000 unique evaluations.  
Greedy exact: 180 path evaluations across six starts.  
Genetic exact: 25,000 unique evaluations using crossover and membership/weight mutation.  
Product-valid exact portfolios: 0.

Best random exact diagnostic: `{'portfolio_hash': '59ae7aea7d25ca5a1aaba8db788208598c31f75d9b91b1318673af252f3c0f96', 'size': 5, 'weights': '0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0.220248217|0|0.1516932475|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0.2183597448|0|0.1848556456|0|0.2248431452|0|0|0|0|0|0', 'dev_final_equity': 0.564445848817274, 'dev_return': -0.435554151182726, 'dev_pf': 0.6030981614174492, 'dev_expectancy_r': -0.0542665831311863, 'dev_maxdd': -2.079203268213431, 'dev_minimum_equity': -77.13131649496502, 'dev_peak_concurrent': 4.0, 'dev_peak_risk': 0.0677949497469062, 'dev_trades': 753.0, 'val_final_equity': 0.9768987070057792, 'val_return': -0.0231012929942208, 'val_pf': 0.9025828221376452, 'val_expectancy_r': -0.0265915852744721, 'val_maxdd': -1.268165321104609, 'val_minimum_equity': -5.14757941838002, 'val_peak_concurrent': 3.0, 'val_peak_risk': 0.0106480452869726, 'val_trades': 161.0, 'oos_final_equity': 1.2801994128991805, 'oos_return': 0.2801994128991802, 'oos_pf': 1.3475442827491575, 'oos_expectancy_r': -0.0951296970027189, 'oos_maxdd': -1.9492069276606188, 'oos_minimum_equity': -336.86567327425604, 'oos_peak_concurrent': 3.0, 'oos_peak_risk': 0.6763302359776292, 'oos_trades': 179.0, 'product_valid': False}`

Best genetic exact diagnostic: `{'portfolio_hash': '14988d16a9f5ce37258567eadbaa7ff59dcc7a33dd09b07dd45325aec95e99a0', 'size': 13, 'weights': '0|0|0.001585264607|0|0|0.0009756774344|0|0|0|0|0|0|0.02329549695|0.000399756345|0|0|0|0|0|0|0|0|0.002584965613|0|0|0|0.01731433551|0|0|0|0.8210702769|0.01226557303|0|0|0|0|0|0|0|2.740034842e-07|0|0|0|0|1.440576014e-05|0|0|0.01282802792|0.0002975740393|0|0|0|0|0|0|0|0|0|0.1073683719|0|0|0|0', 'dev_final_equity': 1.0910344468871087, 'dev_return': 0.0910344468871087, 'dev_pf': 1.2840914539915371, 'dev_expectancy_r': 0.1424963706812834, 'dev_maxdd': -1.4057905896913327, 'dev_minimum_equity': -3.568293238253484, 'dev_peak_concurrent': 6.0, 'dev_peak_risk': 0.0090555806334515, 'dev_trades': 1100.0, 'val_final_equity': 1.063446684756756, 'val_return': 0.063446684756756, 'val_pf': 1.4605457555330192, 'val_expectancy_r': 0.0525865591203724, 'val_maxdd': -1.949585675407292, 'val_minimum_equity': -12.169071529922697, 'val_peak_concurrent': 6.0, 'val_peak_risk': 0.0086495669828154, 'val_trades': 241.0, 'oos_final_equity': 1.0594272700325604, 'oos_return': 0.0594272700325604, 'oos_pf': 1.40268042682021, 'oos_expectancy_r': -0.2482735762528493, 'oos_maxdd': -1.4823431205103954, 'oos_minimum_equity': -1.405283097868185, 'oos_peak_concurrent': 4.0, 'oos_peak_risk': 0.0087727414029049, 'oos_trades': 167.0, 'product_valid': False}`

Best greedy exact diagnostic: `{'seed': 2, 'step': 1, 'size': 2, 'indices': '2|10', 'weights': '0|0|0.5|0|0|0|0|0|0|0|0.5|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0|0', 'dev_final_equity': 1.011787314919796, 'dev_return': 0.011787314919796, 'dev_pf': 1.028362639308924, 'dev_expectancy_r': 0.0202189581915324, 'dev_maxdd': -2.624815644381697, 'dev_minimum_equity': -7.719198662942689, 'dev_peak_concurrent': 2.0, 'dev_peak_risk': 0.0077461518289889, 'dev_trades': 164.0, 'val_final_equity': 1.0541002575294336, 'val_return': 0.0541002575294335, 'val_pf': 1.6484844328819064, 'val_expectancy_r': 0.2618342894011822, 'val_maxdd': -1.0706208252462883, 'val_minimum_equity': -0.1211542412931054, 'val_peak_concurrent': 2.0, 'val_peak_risk': 0.0106798459191274, 'val_trades': 41.0, 'oos_final_equity': 1.0021737710263792, 'oos_return': 0.0021737710263791, 'oos_pf': 1.0185492782498575, 'oos_expectancy_r': 0.0128475663756705, 'oos_maxdd': -1.5203405205561231, 'oos_minimum_equity': -0.520340520556123, 'oos_peak_concurrent': 1.0, 'oos_peak_risk': 0.0050303521578476, 'oos_trades': 44.0, 'product_valid': False}`

No candidate passed all gates across DEV, VAL, and OOS: positive return, PF > 1, positive expectancy, positive equity, sufficient trades, and multi-period support. Risk and execution were not activated.

## Decision

`CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND`

This is conclusive for the current frozen 63-strategy Library under the exact evaluator and fixed 1% total normalized risk convention. No protected evidence was accessed.
