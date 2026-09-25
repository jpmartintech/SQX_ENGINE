# Failure extremes — AUDIT_ONLY

{
  "NZDUSD M15": {
    "count": 0,
    "direction": {},
    "family": {},
    "predicate_count": {},
    "pf": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "expectancy": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "sharpe": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "trade_count": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "drawdown": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "oos_pass_metric_finite": 0
  },
  "USDCHF M15": {
    "count": 0,
    "direction": {},
    "family": {},
    "predicate_count": {},
    "pf": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "expectancy": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "sharpe": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "trade_count": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "drawdown": {
      "p25": null,
      "p50": null,
      "p75": null,
      "p95": null
    },
    "oos_pass_metric_finite": 0
  },
  "XAUUSD H4": {
    "count": 4558,
    "direction": {
      "LONG": 4555,
      "SHORT": 3
    },
    "family": {
      "Trend+Momentum": 680,
      "Trend+Structure": 449,
      "Trend": 232,
      "Trend+Momentum+Structure": 270,
      "Momentum+Volatility+Structure": 163,
      "Momentum+Structure": 580,
      "Structure": 154,
      "Trend+Momentum+Volatility": 247,
      "Momentum": 588,
      "Volatility": 84,
      "Trend+Momentum+Volatility+Structure": 62,
      "Volatility+Structure": 268,
      "Trend+Volatility+Structure": 131,
      "Momentum+Volatility": 389,
      "Trend+Volatility": 261
    },
    "predicate_count": {
      "2": 1854,
      "1": 353,
      "4": 930,
      "3": 1421
    },
    "pf": {
      "p25": 1.5317744177690424,
      "p50": 1.76594092665487,
      "p75": 2.13249477718375,
      "p95": 3.2156944884660965
    },
    "expectancy": {
      "p25": 13.91021251584955,
      "p50": 19.50639825930373,
      "p75": 26.331046692870707,
      "p95": 38.347898992537324
    },
    "sharpe": {
      "p25": 4.05429574093467,
      "p50": 4.966640779798947,
      "p75": 6.09280707753428,
      "p95": 8.665162884682996
    },
    "trade_count": {
      "p25": 53.0,
      "p50": 89.0,
      "p75": 128.0,
      "p95": 172.0
    },
    "drawdown": {
      "p25": 0.1363889732142869,
      "p50": 0.2092897321428585,
      "p75": 0.25957016071428723,
      "p95": 0.3041183428571451
    },
    "oos_pass_metric_finite": 4558
  }
}

NZDUSD M15 and USDCHF M15 have zero retained OOS survivors; the artifacts do not support causal attribution without rerunning trade-level analysis.
