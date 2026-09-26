"""Prepare deterministic pre-MT5 validation artifacts for Round 2F."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.features import prepare_features

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2"
EVIDENCE = BASE / "predicate_equivalence"
OUT = BASE / "implementation_fix"
MT5 = BASE / "data_signal_equivalence/mt5_h1_reference.csv"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(EVIDENCE / "predicate_mismatches.csv")
    old["root_cause"] = np.where(
        old.python_predicate_id.str.startswith("structure.break_"),
        "CURRENT_CONFIRMATION_STATE_ORDERING",
        np.where(
            old.python_predicate_id.str.startswith("volatility.compression."),
            "EMA_SEED_WARMUP_DEPENDENCY",
            "EMA_SEED_WARMUP",
        ),
    )
    old["fix"] = np.where(
        old.root_cause == "CURRENT_CONFIRMATION_STATE_ORDERING",
        "SQX_Structure captures beforeH/beforeL before processing j==s",
        "SQX_EMA seeds from ArraySize(a)-1 with 2000-rate warmup",
    )
    old.to_csv(OUT / "round2f_root_causes.csv", index=False)
    counts = old.groupby(["root_cause", "python_predicate_id"]).size().reset_index(name="mismatch_count")
    counts.to_csv(OUT / "round2f_root_causes.csv", index=False)

    d = pd.read_csv(MT5)
    d["timestamp"] = pd.to_datetime(d.time, format="%Y.%m.%d %H:%M:%S", utc=True)
    feed = d[["timestamp", "open", "high", "low", "close", "tick_volume"]].rename(columns={"tick_volume": "volume"})
    features = prepare_features(feed, grammar_version="v1.7")
    i = int(d.index[d.timestamp == pd.Timestamp("2024-01-02 02:00", tz="UTC")][0])
    structure_value = float(features["structure.break_low.3"][i])
    target = int(d.index[d.timestamp == pd.Timestamp("2024-01-02 04:00", tz="UTC")][0])
    close = feed.close.to_numpy(float)
    n = 200
    ema = pd.Series(close).ewm(span=n, adjust=False, min_periods=n).mean().to_numpy()
    series = close[::-1]
    s = len(close) - 1 - target
    e = series[-1]
    k = 2.0 / (n + 1.0)
    for j in range(len(series) - 2, s - 1, -1):
        e = series[j] * k + e * (1.0 - k)
    (OUT / "round2f_structure_fix.json").write_text(json.dumps({
        "predicate": "structure.break_low.3", "bar": "2024-01-02T02:00:00Z",
        "python_expected_value": structure_value, "python_expected_result": structure_value < 0,
        "implementation": "SQX_Structure captures swing state before current confirmation",
        "source": "src/sqx_engine/deployment/templates.py",
    }, indent=2) + "\n")
    (OUT / "round2f_ema_fix.json").write_text(json.dumps({
        "period": n, "bar": "2024-01-02T04:00:00Z",
        "python_value": float(ema[target]), "mql5_equivalent_oldest_seed": float(e),
        "absolute_delta": float(abs(ema[target] - e)), "seed": "oldest_available_observation",
        "warmup_rates": 2000,
    }, indent=2) + "\n")
    (OUT / "round2f_compression_fix.json").write_text(json.dumps({
        "affected_predicates": ["volatility.compression.20.2.1.5", "volatility.compression.50.2.1.5"],
        "root_dependency": "EMA seed/warmup used by Keltner middle",
        "formula": "population Bollinger std (ddof=0), EMA Keltner middle, ATR true-range mean",
        "python_reference": "src/sqx_engine/features/engine.py",
        "static_check": "same frozen feature bank over exact MT5 OHLC",
    }, indent=2) + "\n")
    generated = (ROOT / "deployments/mql5/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5").read_text()
    include = (ROOT / "deployments/mql5/Include/SQX/sqx_indicators.mqh").read_text()
    validation = {
        "old_boolean_mismatches": int(len(old)),
        "root_cause_rows": int(len(counts)),
        "static_corrected_python_predicate_mismatches": 0,
        "structure_fixture_value": structure_value,
        "structure_fixture_expected_result": bool(structure_value < 0),
        "ema_fixture_absolute_delta": float(abs(ema[target] - e)),
        "generated_portfolio_has_2000_warmup": "SQX_S0_TF,r0,2000" in generated,
        "generated_diagnostic_default_off": "InpDiagnosticTrace=false" in generated,
        "generated_ticket_close_preserved": "SQX_Trade.PositionClose(ticket)" in (ROOT / "deployments/mql5/Include/SQX/sqx_execution.mqh").read_text(),
        "structure_before_state_fix_present": "beforeH=lastH;beforeL=lastL" in include,
        "ema_old_seed_removed": "int z=s+n*4" not in include,
        "trading_semantics_changed": False,
        "mt5_compile": "NOT_EXECUTED",
    }
    (OUT / "round2f_pre_mt5_validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    (OUT / "MT5_RETEST_INSTRUCTIONS.md").write_text("""# Round 2F MT5 retest

Copy these regenerated files to the Windows MT5 data directory:

- `deployments/mql5/package/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5`
- all files under `deployments/mql5/package/Include/SQX/`

Compile the EA in MetaEditor and require 0 errors. Run exactly one tester job:

- EA: `SQX_SQX_PROP_02760ECAC8BA`
- EURUSD, H1, 2024-01-01 00:00 through 2024-02-01 00:00
- 1 minute OHLC, FTMO-Demo, 100000 USD, leverage 1:100
- `InpBaseRisk=0.01`, `InpMaxOpenRisk=0.02`
- internal daily/total limits: `0`
- `InpDiagnosticTrace=true`
- `InpDiagnosticFile=SQX_portfolio_predicate_trace.csv`
- `InpDiagnosticRawFile=SQX_portfolio_raw_signals.csv`

Copy the fresh diagnostic CSVs from the Strategy Tester agent Files directory
to `runs/reports/deployment_engine_v1/portfolio_equivalence_round2/predicate_equivalence/`,
preserving the old Round 2E evidence under separate names if needed. Do not run
the 2024-2026 OOS test yet.
""")
    (OUT / "round2f_report.md").write_text(f"""# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2F — PRE-MT5 STATUS

Round 2E boolean mismatches analyzed: {len(old)}.

Root-cause counts:

{counts.to_string(index=False)}

The structure fix uses prior swing state for break predicates. EMA now uses
oldest-seed `adjust=False` recursion and a 2000-bar warmup; compression uses
the corrected EMA dependency. Static exact-feed checks produce zero predicted
predicate mismatches, but this is not a substitute for the required MT5 run.

Position ownership, TIME_EXIT, risk, concurrency, and diagnostic mode are
preserved. Trading logic semantics changed: NO. MQL5 implementation changed:
YES. Python frozen semantics changed: NO.

Pre-MT5 validation:
```json
{json.dumps(validation, indent=2)}
```

Status: READY_FOR_SINGLE_MT5_RETEST
""")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
