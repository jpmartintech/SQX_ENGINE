# SQX CRYPTO CLEAN REBOOT V1 — MANUFACTURING FINAL STATUS

Starting commit: e2f6311
PRE-VAL freeze commit: 1bf4bb1
VAL commit: 099e647
PRE-OOS freeze commit: 0fe11c6

## Firewall

DEV accessed. VAL accessed only after PRE-VAL freeze. OOS accessed once after PRE-OOS freeze. LOCKBOX accesses: 0.

## Manufacturing

Random exact unique: 50,000. Genetic exact unique: 200,000. Total: 250,000.
Random duplicate attempts: 18,926. Genetic duplicate attempts: 567.

## DEV

Frozen DEV candidates: 17,922 (Random 3,051; Genetic 14,871). The exact funnel is in `dev_candidate_funnel.csv`.

## VAL / Library

VAL-admitted Library: 7634 records, representing 7350 unique strategy hashes (5502 LONG / 2132 SHORT records). Cross-lineage duplicate hashes are retained diagnostically and must be deduplicated before Portfolio Factory.

## OOS (burned research evidence only)

Admitted OOS: {'count': 7634, 'positive_return': 4156, 'positive_rate': 0.5444066020434897, 'positive_expectancy': 4156, 'median_return': 0.017644266949178977, 'median_expectancy': 6.118532106351195e-05, 'median_pf': 1.0118489080010185, 'p75_return': 0.10134777134320111, 'p90_return': 0.24368399035504157, 'p95_return': 0.35164630788075746, 'p99_return': 0.6113334522757244, 'ruin_rate': 0.08606235263295782}
Rejected-but-valid OOS: {'count': 43904, 'positive_return': 18339, 'positive_rate': 0.4177068148688047, 'positive_expectancy': 18339, 'median_return': -0.031432571413141985, 'median_expectancy': -6.940523006925328e-05, 'median_pf': 0.9850793654015877, 'p75_return': 0.08890030840562557, 'p90_return': 0.256211195774066, 'p95_return': 0.38779228102173713, 'p99_return': 0.688025929420845, 'ruin_rate': 0.14857416180758018}

Admission increased positive-return rate by 0.127 and median return by 0.0491. Among unique frozen Library hashes, aligned OOS daily normalized-R correlation has median 0.018, downside correlation median 0.013, and drawdown-overlap median 0.887; these are descriptive and not portfolio optimization.

## Decision

PRICE_ONLY_FACTORY_SUPPORTED

The frozen DEV+VAL process produced a large Library and materially enriched burned OOS profitability. This is not protected validation; the next step is Portfolio Factory, with no LOCKBOX access in this loop.
