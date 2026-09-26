# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2F — PRE-MT5 STATUS

Round 2E boolean mismatches analyzed: 197.

Root-cause counts:

                         root_cause             python_predicate_id  mismatch_count
CURRENT_CONFIRMATION_STATE_ORDERING          structure.break_high.2              48
CURRENT_CONFIRMATION_STATE_ORDERING           structure.break_low.3              12
CURRENT_CONFIRMATION_STATE_ORDERING           structure.break_low.5               6
                    EMA_SEED_WARMUP              trend.close_ema.10               2
                    EMA_SEED_WARMUP           trend.ema_pair.50.100               1
                    EMA_SEED_WARMUP            trend.ema_slope.10.3               1
                    EMA_SEED_WARMUP           trend.ema_slope.100.3               2
                    EMA_SEED_WARMUP           trend.ema_slope.200.1               4
                    EMA_SEED_WARMUP            trend.ema_slope.50.3               6
         EMA_SEED_WARMUP_DEPENDENCY volatility.compression.20.2.1.5              49
         EMA_SEED_WARMUP_DEPENDENCY volatility.compression.50.2.1.5              66

The structure fix uses prior swing state for break predicates. EMA now uses
oldest-seed `adjust=False` recursion and a 2000-bar warmup; compression uses
the corrected EMA dependency. Static exact-feed checks produce zero predicted
predicate mismatches, but this is not a substitute for the required MT5 run.

Position ownership, TIME_EXIT, risk, concurrency, and diagnostic mode are
preserved. Trading logic semantics changed: NO. MQL5 implementation changed:
YES. Python frozen semantics changed: NO.

Pre-MT5 validation:
```json
{
  "old_boolean_mismatches": 197,
  "root_cause_rows": 11,
  "static_corrected_python_predicate_mismatches": 0,
  "structure_fixture_value": -0.0004300000000001525,
  "structure_fixture_expected_result": true,
  "ema_fixture_absolute_delta": 0.0,
  "generated_portfolio_has_2000_warmup": true,
  "generated_diagnostic_default_off": true,
  "generated_ticket_close_preserved": true,
  "structure_before_state_fix_present": true,
  "ema_old_seed_removed": true,
  "trading_semantics_changed": false,
  "mt5_compile": "NOT_EXECUTED"
}
```

Status: READY_FOR_SINGLE_MT5_RETEST
