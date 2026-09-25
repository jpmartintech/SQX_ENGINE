# SQX LIBRARY AUDIT — FINAL STATUS

Library strategies: **12,289**
Production strategies: **11,986** (policy members; 11,990 V1.8 rows include 4 smoke rows)
Legacy strategies: **299**

Structural clusters: **11,340**
Behavioral clusters: **NOT AVAILABLE** (no trade/equity series retained)
Effective strategy count estimate: **11,340** (structural near-duplicate components only)
Median behavioral correlation: **NOT AVAILABLE**
Strategies with |corr| >= 0.80 neighbour: **NOT AVAILABLE**
Strategies with |corr| >= 0.95 neighbour: **NOT AVAILABLE**
Temporally stable: **NOT AVAILABLE**
Cost robust 1.5x: **NOT AVAILABLE**
Cost robust 2.0x: **NOT AVAILABLE**
XAUUSD H4 integrity: **PASS_STATIC_PROVENANCE_AND_UNITS**
LONG/SHORT asymmetry: **OBSERVED: 10,628 / 1,661**
Seed redundancy: **PARTIAL_OBSERVATIONAL_OVERLAP**
Multi-asset readiness: **CONFIG_ONLY / CODE_CHANGE_REQUIRED depending on capability**
Tests: **87 passed**
Golden regression: **PASS**
Factory integrity: **PASS**

## 1. Executive findings

- **OBSERVED:** canonical dedup is exact: 12,289 rows and 12,289 distinct canonical hashes.
- **OBSERVED:** 10,603 of 11,340 structural components are singletons; the largest component has 7 members.
- **OBSERVED:** XAUUSD H4 contributes 4,558 library strategies and had 4,847 OOS observations, with 98.54% Validation→OOS survival.
- **NOT ESTABLISHED:** behavioral independence, temporal half-OOS stability, and cost robustness beyond stored production metrics; immutable artifacts contain no trade ledger, entry timestamps, equity curves, or cost-scenario outputs.
- **INFERRED:** the structural estimate of 11,340 is only a redundancy-adjusted rule-signature view, not an alpha or portfolio count.

## 2. Inventory

{
  "direction": {
    "LONG": 10628,
    "SHORT": 1661
  },
  "family": {
    "Momentum": 851,
    "Momentum+Structure": 1248,
    "Momentum+Volatility": 840,
    "Momentum+Volatility+Structure": 580,
    "Structure": 296,
    "Trend": 602,
    "Trend+Momentum": 1532,
    "Trend+Momentum+Structure": 1028,
    "Trend+Momentum+Volatility": 944,
    "Trend+Momentum+Volatility+Structure": 354,
    "Trend+Structure": 1181,
    "Trend+Volatility": 1066,
    "Trend+Volatility+Structure": 884,
    "Volatility": 229,
    "Volatility+Structure": 654
  },
  "legacy": 299,
  "market": {
    "EURUSD": 1762,
    "GBPUSD": 820,
    "NZDUSD": 121,
    "USDCAD": 285,
    "USDCHF": 570,
    "USDJPY": 2806,
    "XAUUSD": 5925
  },
  "market_timeframe": {
    "EURUSD H1": 948,
    "EURUSD H4": 730,
    "EURUSD M15": 84,
    "GBPUSD H1": 212,
    "GBPUSD H4": 481,
    "GBPUSD M15": 127,
    "NZDUSD H1": 3,
    "NZDUSD H4": 118,
    "USDCAD H1": 44,
    "USDCAD H4": 240,
    "USDCAD M15": 1,
    "USDCHF H1": 8,
    "USDCHF H4": 562,
    "USDJPY H1": 1032,
    "USDJPY H4": 1622,
    "USDJPY M15": 152,
    "XAUUSD H1": 1340,
    "XAUUSD H4": 4558,
    "XAUUSD M15": 27
  },
  "predicate_count": {
    "1": 473,
    "2": 3964,
    "3": 4202,
    "4": 3650
  },
  "production": 11990,
  "production_policy": 11986,
  "promotion_level": {
    "OOS_PASS": 12289
  },
  "seed": {
    "1301": 4076,
    "1302": 4346,
    "1303": 3867
  },
  "smoke": 4,
  "timeframe": {
    "H1": 3587,
    "H4": 8311,
    "M15": 391
  }
}

## 3. Structural diversity

Method: union of exact canonical signatures and near predicate-set Jaccard >= 0.8 within market/timeframe/direction/predicate-count, same ATR period/time exit; AUDIT_ONLY
Exact canonical signatures: 12,289; near-duplicate members: 1,686; singletons: 10,603; largest sizes: [7, 7, 7, 6, 5, 5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4]
Jaccard/family/parameter details are in `structural_clusters.csv` and `structural_summary.json`.

## 4. Behavioral diversity

NOT AVAILABLE without trade/equity series. Empty `behavioral_clusters.csv` is intentional; no behavioral claims were inferred from aggregate PF/Sharpe values.

## 5. Temporal stability

NOT AVAILABLE: no OOS subperiod or yearly trade-level metrics are stored.

## 6. Cost sensitivity

NOT AVAILABLE: the library stores frozen production results, but not 1.25x/1.5x/2.0x scenario result vectors. No retroactive cost gate was applied.

## 7. XAUUSD H4 investigation

Integrity and provenance checks pass. No date overlap, profile hash mismatch, unit failure, or validation/OOS artifact reuse was found in frozen audit records. The retained data cannot identify whether the high survival is caused by volatility, sample structure, grammar compatibility or another factor without trade-level analysis. See `xauusd_h4_investigation.md`.

## 8. Failure extremes

NZDUSD M15 (29 Dev, 0 Val, 0 OOS) and USDCHF M15 (25 Dev, 0 Val, 0 OOS) are recorded descriptively. Causal attribution is not established from aggregate artifacts. See `failure_extremes.md`.

## 9. LONG / SHORT

Library survivors are 86.49% LONG and 13.51% SHORT. Breakdown by market, timeframe, family and predicate count is in `long_short_analysis.md`. This does not isolate search, market or gate causality.

## 10. Seed redundancy

Seed overlap is computed only from retained promotion observations and is therefore partial. Full generated-population overlap is unavailable without discovery-level identity joins beyond retained library observations.

## 11. Market × timeframe quality map

See `market_timeframe_quality.csv`; it reports library count and stored OOS metric medians. Behavioral diversity, temporal stability and cost sensitivity are explicitly marked unavailable.

## 12. Multi-asset readiness

# Multi-asset compatibility audit — AUDIT_ONLY

|Area|Status|Finding|
|---|---|---|
|market/timeframe identity|READY|First-class in StrategyDefinition/library identity|
|pip/tick scale|CONFIG_ONLY|Execution profiles carry pip/tick scale; new instruments need reviewed profiles|
|point value/contract size|UNRESOLVED|Not represented as a general futures contract model|
|quote currency/conversion|CODE_CHANGE_REQUIRED|No general multi-currency accounting layer|
|sessions/24-7 calendars|CODE_CHANGE_REQUIRED|Current temporal/data handling is bar-series based|
|commission/funding|CODE_CHANGE_REQUIRED|Frozen model has no general commission/funding/rollover abstraction|
|futures expiry/rollover|UNRESOLVED|No continuous-contract policy|
|timezone|CONFIG_ONLY|Dataset provenance preserves timestamp convention; per-market audit required|
|crypto|CODE_CHANGE_REQUIRED|No production-ready crypto execution model|


## 13. Resource/performance

Audit runtime: 3.01s; peak RSS: 194.7 MiB. Structural analysis used inverted-index candidate pairs and did not allocate a dense 12,289×12,289 matrix.

## 14. Integrity

{
  "audit_only": true,
  "canonical_dedup": "PASS",
  "database_integrity": "ok",
  "distinct_canonical_hashes": 12289,
  "factory_modified": false,
  "observations": 12771,
  "status": "PASS",
  "strategy_rows": 12289
}

## 15. Conclusions

**OBSERVED:** the Library is internally consistent and structurally diverse under the stated rule-signature method. **INFERRED:** structural redundancy reduces the descriptive count from 12,289 to approximately 11,340 components under this threshold. **NOT ESTABLISHED:** independent alpha sources, future edge, behavioral diversification, temporal stability, or cost robustness. No factory, gate, execution assumption, canonical hash, or historical result was modified.
