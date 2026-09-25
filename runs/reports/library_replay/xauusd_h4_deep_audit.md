# XAUUSD H4 — DEEP AUDIT_ONLY

{
  "behavioral": [
    {
      "market": "XAUUSD",
      "timeframe": "H4",
      "strategies": 4558,
      "timestamp_points": 1698,
      "p5": 0.029875443130731583,
      "p25": 0.106356892734766,
      "p50": 0.1820843368768692,
      "p75": 0.28377725183963776,
      "p90": 0.4012097120285034,
      "p95": 0.4825116753578187,
      "p99": 0.6489738774299623,
      "ge_050": 0.042719189616426054,
      "ge_070": 0.005745564230872889,
      "ge_080": 0.0023559990883358114,
      "ge_090": 0.0008144123054252204,
      "ge_095": 0.0003555952522978646,
      "nearest_median": 0.8473370373249054,
      "components_corr_080": 1444,
      "singletons_corr_080": 1072,
      "largest_corr_080": 1578,
      "effective_rank": 1313.0
    }
  ],
  "oos_observations": 4847,
  "validation_to_oos": 0.9853628786,
  "note": "Replay used frozen V1.8 evaluator; no production artifacts modified."
}

The replay establishes timestamp-aligned return behavior for the retained OOS segments. It does not establish future edge or causal explanation for the high survival rate.
