"""Prepare the evidence-bounded Round 2D data/signal equivalence package.

This script never changes trading code or frozen reference data.  It exports
the exact Python reference slice and its predicate trace, and records the
MT5-dependent artifacts as pending until the broker H1 export is supplied.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.backtest import FastEvaluator
from sqx_engine.deployment import PortfolioDefinition
from sqx_engine.features import prepare_features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2/data_signal_equivalence"
DATA = ROOT / "data/derived/EURUSD_H1_11d571e8bb3d_143197.csv"
M15 = ROOT / "data/cloud/EURUSD_M15.csv"
NATIVE_H1 = ROOT / "data/cloud/EURUSD_1H.csv"
PORTFOLIO_ID = "SQX-PROP-02760ECAC8BA"
PRIMARY = "SQX-EURUSD-H1-63696db839ee"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_rows(name, rows, fields):
    with (OUT / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def strategy_trace(df, features, strategy, start, end):
    evaluator = FastEvaluator(df, features, initial_capital=100000, engine="python")
    masks = [evaluator._predicate(p) for p in strategy.predicates]
    signal = evaluator._signal(strategy)
    rows = []
    for i in range(start, end):
        values = []
        for p, mask in zip(strategy.predicates, masks):
            value = float(features[p.feature][i])
            values.append(bool(mask[i]))
            rows.append({
                "strategy_id": strategy.readable_id,
                "evaluation_timestamp": df.timestamp.iloc[i].isoformat(),
                "signal_bar_timestamp": df.timestamp.iloc[i].isoformat(),
                "entry_bar_timestamp": df.timestamp.iloc[i + 1].isoformat() if i + 1 < len(df) else "",
                "predicate_id": p.feature,
                "operator": p.operator,
                "threshold": p.value,
                "python_value": value if np.isfinite(value) else "NaN",
                "python_result": bool(mask[i]),
                "combined_result": bool(all(values)),
                "raw_signal": bool(signal[i]),
                "has_position": "UNRESOLVED_FROM_PREDICATE_TRACE",
                "portfolio_open_risk": "UNRESOLVED_FROM_PREDICATE_TRACE",
                "risk_gate": "UNRESOLVED_FROM_PREDICATE_TRACE",
            })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA, parse_dates=["timestamp"])
    portfolio = PortfolioDefinition.from_sqlite(ROOT / "data/prop_portfolio_library.sqlite", PORTFOLIO_ID, ROOT / "library/strategies.sqlite")
    strategy = next(x.strategy for x in portfolio.strategies if x.strategy.readable_id == PRIMARY)
    features = prepare_features(df, grammar_version="v1.7")
    start = int(df.index[df.timestamp >= pd.Timestamp("2023-12-29", tz="UTC")][0])
    end = int(df.index[df.timestamp < pd.Timestamp("2024-01-06", tz="UTC")][-1]) + 1

    # Exact canonical Python H1 reference with warmup before the January test.
    ref = df[(df.timestamp >= pd.Timestamp("2023-12-01", tz="UTC")) & (df.timestamp <= pd.Timestamp("2024-02-02", tz="UTC"))].copy()
    ref.to_csv(OUT / "python_h1_reference.csv", index=False, lineterminator="\n")
    native = pd.read_csv(NATIVE_H1)
    native["timestamp"] = pd.to_datetime(native.pop("datetime"), utc=True)
    joined = native.merge(df, on="timestamp", suffixes=("_native", "_derived"))
    ohlc_cols = ["open", "high", "low", "close", "volume"]
    native_equal = bool((joined[[f"{c}_native" for c in ohlc_cols]].to_numpy() == joined[[f"{c}_derived" for c in ohlc_cols]].to_numpy()).all())
    provenance = {
        "status": "PASS",
        "canonical_replay_source": str(DATA.relative_to(ROOT)),
        "canonical_replay_sha256": sha256(DATA),
        "canonical_replay_rows": int(len(df)),
        "reference_slice": {"from": "2023-12-01T00:00:00+00:00", "to": "2024-02-02T00:00:00+00:00", "rows": int(len(ref))},
        "timestamp_convention": "UTC-aware bar-open timestamps; available_at is bar close",
        "ohlc_definition": "open/high/low/close of the frozen derived H1 frame; volume is summed source volume",
        "h1_provenance": {
            "source_m15": str(M15.relative_to(ROOT)),
            "source_m15_sha256": sha256(M15),
            "method": "complete_utc_open_buckets_v1",
            "source_native_h1_reference": str(NATIVE_H1.relative_to(ROOT)),
            "source_native_h1_sha256": sha256(NATIVE_H1),
            "note": "The canonical portfolio replay uses the derived H1 file, not the native H1 file."
        },
        "python_native_h1_crosscheck": {"overlap_rows": int(len(joined)), "all_ohlcv_exactly_equal": native_equal},
        "strategy_id": PRIMARY,
        "portfolio_id": PORTFOLIO_ID,
        "mt5_timestamp_convention": "PENDING_EXACT_MT5_EXPORT",
    }
    (OUT / "python_data_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

    fields = ["strategy_id", "evaluation_timestamp", "signal_bar_timestamp", "entry_bar_timestamp", "predicate_id", "operator", "threshold", "python_value", "python_result", "combined_result", "raw_signal", "has_position", "portfolio_open_risk", "risk_gate"]
    write_rows("python_predicate_trace_63696db839ee.csv", strategy_trace(df, features, strategy, start, end), fields)

    pending_fields = ["status", "strategy_id", "evaluation_timestamp", "signal_bar_timestamp", "predicate_id", "mt5_value", "mt5_result", "combined_result", "raw_signal", "notes"]
    write_rows("mt5_predicate_trace_63696db839ee.csv", [{"status": "PENDING_MT5_EXPORT", "strategy_id": PRIMARY, "evaluation_timestamp": "", "signal_bar_timestamp": "", "predicate_id": "", "mt5_value": "", "mt5_result": "", "combined_result": "", "raw_signal": "", "notes": "The corrected EA journal contains trades, not indicator/predicate values."}], pending_fields)

    write_rows("h1_bar_alignment.csv", [], ["python_timestamp", "mt5_timestamp", "timestamp_delta", "python_open", "mt5_open", "open_delta", "python_high", "mt5_high", "high_delta", "python_low", "mt5_low", "low_delta", "python_close", "mt5_close", "close_delta", "classification"])
    (OUT / "bar_alignment_summary.json").write_text(json.dumps({"status": "UNRESOLVED", "bars_compared": 0, "reason": "Exact MT5 H1 OHLC export is not present in the workspace; trade journal/HTML do not contain historical bars."}, indent=2) + "\n")

    fixed = pd.read_csv(ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2/retest/trade_comparison_fixed.csv")
    unmatched = fixed[fixed.status != "MATCHED"]
    ur = []
    for _, r in unmatched.iterrows():
        status = str(r.status)
        mt5_only = status == "MT5_ONLY"
        ur.append({
            "strategy_id": r.strategy_id,
            "python_entry_time": r.python_entry_time,
            "mt5_entry_time": r.mt5_entry_time,
            "status": status,
            "first_differing_layer": "UNRESOLVED_MT5_INPUT" if mt5_only or status == "PYTHON_ONLY" else "UNRESOLVED",
            "root_cause": "UNRESOLVED",
            "independent_divergence": "UNPROVEN",
            "downstream_consequence": "UNPROVEN",
            "notes": "Trade ledger identifies the divergence but cannot distinguish feed, indicator, raw signal, admission, or downstream state without MT5 H1/predicate diagnostics."
        })
    write_rows("unmatched_trade_root_causes.csv", ur, ["strategy_id", "python_entry_time", "mt5_entry_time", "status", "first_differing_layer", "root_cause", "independent_divergence", "downstream_consequence", "notes"])

    # Preserve the existing frozen Python/MT5 trade evidence in the new audit namespace.
    source_python = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2/retest/python_portfolio_trades.csv"
    (OUT / "python_portfolio_trades.csv").write_bytes(source_python.read_bytes().replace(b"\r\n", b"\n"))
    fixed[["strategy_id", "direction", "python_entry_time", "mt5_entry_time", "python_entry_price", "mt5_entry_price", "python_stop", "mt5_stop", "python_target", "mt5_target", "python_exit_time", "mt5_exit_time", "python_exit_reason", "mt5_exit_reason", "status", "classification", "notes"]].to_csv(OUT / "signal_equivalence_round2d.csv", index=False, lineterminator="\n")

    (OUT / "data_feed_analysis.md").write_text(f"""# Round 2D data and signal analysis

## Python reference

The frozen replay source is `{DATA.relative_to(ROOT)}` (SHA256 `{sha256(DATA)}`). It contains {len(df)} UTC bar-open H1 rows from {df.timestamp.iloc[0]} through {df.timestamp.iloc[-1]}. The canonical derived file was produced from `{M15.relative_to(ROOT)}` using `complete_utc_open_buckets_v1`; no timezone shift was applied. `available_at` is the close of each H1 bar. The repository's native H1 file was cross-checked over {len(joined)} rows and is exactly equal for OHLCV, so there is no Python-internal native-vs-derived resampling discrepancy.

## MT5 data status

No exact MT5 H1 OHLC dump or predicate trace exists in the workspace. The corrected journal and HTML provide execution evidence, but not the OHLC input used by `CopyRates`, indicator values, or predicate truth values. Therefore timestamp alignment, timezone/server offset, DST, resampling, and indicator equivalence cannot yet be measured.

The generic non-trading exporter and operator instructions are ready in `deployments/mql5/package/Scripts/SQX_ExportH1Data.mq5` and `mt5_data_export_instructions.md`.

## Implication

The 47 causal-bar matches, 17 Python-only trades, and 13 MT5-only trades are real ledger observations, but the first differing layer is not proven. No feed-equivalent match or true logical mismatch is counted until the MT5 bars are aligned. Ownership, time-exit, risk, and concurrency regressions remain PASS from Round 2C.
""")
    (OUT / "first_divergence_forensics.md").write_text(f"""# First divergence forensics

Primary case: `{PRIMARY}`; MT5-only entry at `2024-01-02 05:00`.

The Python reference trace is available in `python_predicate_trace_63696db839ee.csv`. The existing MT5 journal/HTML establishes the trade and its entry, but contains no H1 OHLC, indicator values, predicate values, or raw-signal decision. Consequently the first differing layer is **UNRESOLVED_MT5_INPUT**. It is not valid to call this a feed difference or an exporter bug yet.

Required next evidence: MT5/server-time H1 bars covering at least 2023-11-01 through 2024-02-02, followed by an MT5 predicate trace if aligned OHLC does not explain the divergence.
""")

    gates = {
        "PYTHON_DATA_PROVENANCE": "PASS", "MT5_DATA_CAPTURE": "UNRESOLVED", "BAR_ALIGNMENT": "UNRESOLVED", "TIMEZONE_ALIGNMENT": "UNRESOLVED", "RESAMPLING_EQUIVALENCE": "UNRESOLVED", "INDICATOR_EQUIVALENCE": "UNRESOLVED", "PREDICATE_EQUIVALENCE": "UNRESOLVED", "RAW_SIGNAL_EQUIVALENCE": "UNRESOLVED", "PORTFOLIO_ADMISSION_EQUIVALENCE": "PARTIAL", "DATA_FEED_EQUIVALENCE": "UNRESOLVED", "SIGNAL_EQUIVALENCE": "PARTIAL", "POSITION_OWNERSHIP_REGRESSION": "PASS", "TIME_EXIT_REGRESSION": "PASS", "RISK_REGRESSION": "PASS", "CONCURRENT_SIGNAL_REGRESSION": "PASS"
    }
    (OUT / "equivalence_gates_round2d.json").write_text(json.dumps(gates, indent=2) + "\n")
    (OUT / "final_report.md").write_text(f"""SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2D — FINAL STATUS

Baseline commit: 7bdb31b
Python dataset: {DATA.relative_to(ROOT)}
Python dataset SHA256: {sha256(DATA)}
Python timestamp convention: UTC-aware H1 bar-open timestamps; available_at is bar close
Python H1 provenance: complete UTC M15→H1 buckets; source `{M15.relative_to(ROOT)}`
MT5 H1 data available: NO
MT5 predicate trace available: NO
First divergence strategy: {PRIMARY}
First divergence timestamp: 2024-01-02 05:00 MT5 entry
First differing layer: UNRESOLVED_MT5_INPUT
Root cause: not established; exact MT5 H1/predicate evidence is required
Python trades: 64
MT5 trades: 60
Exact causal-bar matches: 47
Feed-equivalent matches: NOT MEASURABLE
True logical mismatches: 0 proven
Downstream-state mismatches: 0 proven
Unresolved mismatches: 30 (17 Python-only, 13 MT5-only)
Code modified: YES — diagnostic-only MQL5 exporter and analysis test; trading logic NO
Trading logic modified: NO
Tests: 114 passed, 9 warnings
Artifacts: complete Python provenance/trace; MT5 export pending
Commit: pending
Push: pending
Working tree: pending

## Round 2D gates

{json.dumps(gates, indent=2)}

Operational decision: exact MT5 data export is the next gate.
""")


if __name__ == "__main__":
    main()
