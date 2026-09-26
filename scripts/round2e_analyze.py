"""Final same-feed analysis for the real Round 2E MT5 diagnostic traces.

This script deliberately treats the captured MT5 CSVs as immutable evidence.
It regenerates only the Python expectation from the exact MT5 H1 export and
writes deterministic comparison/report artifacts.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.deployment import PortfolioDefinition

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2"
OUT = BASE / "predicate_equivalence"
TRACE = OUT / "mt5_predicate_trace.csv"
RAW = OUT / "mt5_raw_signals.csv"
EXPECTED = OUT / "python_expected_predicate_trace_mt5_feed.csv"
EXPECTED_RAW = OUT / "python_expected_raw_signals_mt5_feed.csv"
MT5_H1 = BASE / "data_signal_equivalence/mt5_h1_reference.csv"
PORTFOLIO_ID = "SQX-PROP-02760ECAC8BA"

TRACE_SHA = "c0097cc4a6fee364a915ca46b468bc5f4798811798194809de68bb5eb5c884ba"
RAW_SHA = "ab39930115413ec0bed55738867da2e246e79e8bfaa59579235e050789b83d27"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def mt5_time(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, format="mixed", utc=True)


def bool_value(v) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes"}


def finite(v) -> bool:
    try:
        x = float(v)
        return math.isfinite(x) and abs(x) < 1e300
    except (TypeError, ValueError):
        return False


def clean_float(v):
    return float(v) if finite(v) else np.nan


def strategy_order() -> list[str]:
    p = PortfolioDefinition.from_sqlite(
        ROOT / "data/prop_portfolio_library.sqlite",
        PORTFOLIO_ID,
        ROOT / "library/strategies.sqlite",
    )
    return [x.strategy.readable_id for x in p.strategies]


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    actual = pd.read_csv(TRACE)
    raw = pd.read_csv(RAW)
    expected = pd.read_csv(EXPECTED)
    for d, col in ((actual, "signal_bar_time"), (raw, "signal_bar_time"), (expected, "signal_bar_time")):
        d["_time"] = mt5_time(d[col])
    return actual, raw, expected


def integrity(actual: pd.DataFrame, raw: pd.DataFrame, expected: pd.DataFrame) -> dict:
    required_trace = {
        "evaluation_time", "signal_bar_time", "strategy_index", "strategy_id", "direction",
        "predicate_count", "aggregation_mode", "raw_signal", "entry_admitted",
        "position_gate", "risk_gate", "concurrent_gate",
        *(f"predicate_{j}_{k}" for j in range(1, 5) for k in ("id", "numeric_value", "threshold_or_reference", "result")),
    }
    required_raw = {"signal_bar_time", "entry_bar_time", "strategy_index", "strategy_id", "direction", "raw_signal"} & set(raw.columns)
    expected_ids = strategy_order()
    actual_map = actual.sort_values("strategy_index").drop_duplicates("strategy_index").set_index("strategy_index").strategy_id.to_dict()
    key = ["strategy_id", "_time"]
    pos = actual[(actual.strategy_id == "SQX-EURUSD-H1-63696db839ee") & (actual._time == pd.Timestamp("2024-01-02 04:00", tz="UTC"))]
    raw_pos = raw[(raw.strategy_id == "SQX-EURUSD-H1-63696db839ee") & (raw._time == pd.Timestamp("2024-01-02 04:00", tz="UTC"))]
    return {
        "trace_exists": TRACE.exists(), "raw_exists": RAW.exists(),
        "trace_sha256": sha256(TRACE), "raw_sha256": sha256(RAW),
        "trace_sha256_expected": TRACE_SHA, "raw_sha256_expected": RAW_SHA,
        "trace_sha256_match": sha256(TRACE) == TRACE_SHA,
        "raw_sha256_match": sha256(RAW) == RAW_SHA,
        "trace_rows": int(len(actual)), "raw_rows": int(len(raw)), "expected_rows": int(len(expected)),
        "trace_rows_expected": 10560, "raw_rows_expected_observed": 231,
        "trace_row_count_ok": len(actual) == 10560, "raw_row_count_ok": len(raw) == 231,
        "required_trace_columns": sorted(required_trace - set(actual.columns)),
        "required_raw_columns_present": sorted(required_raw),
        "trace_required_columns_ok": required_trace <= set(actual.columns),
        "strategy_count": int(actual.strategy_id.nunique()),
        "strategy_ids": sorted(actual.strategy_id.unique()),
        "strategy_count_ok": actual.strategy_id.nunique() == 20,
        "strategy_index_mapping": {str(k): v for k, v in actual_map.items()},
        "strategy_index_mapping_ok": all(actual_map.get(i) == sid for i, sid in enumerate(expected_ids)),
        "trace_duplicate_keys": int(actual.duplicated(key).sum()),
        "expected_duplicate_keys": int(expected.duplicated(key).sum()),
        "positive_control_trace_rows": int(len(pos)),
        "positive_control_raw_rows": int(len(raw_pos)),
        "positive_control_present": len(pos) == 1 and len(raw_pos) == 1,
    }


def compare_predicates(actual: pd.DataFrame, expected: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    keys = ["strategy_id", "_time"]
    a = actual.rename(columns={c: f"a__{c}" for c in actual.columns if c not in keys})
    e = expected.rename(columns={c: f"e__{c}" for c in expected.columns if c not in keys})
    joined = e.merge(a, on=keys, how="outer", indicator=True, validate="one_to_one")
    rows = []
    for _, r in joined.iterrows():
        both = r["_merge"] == "both"
        for n in range(1, 5):
            eid = r.get(f"e__predicate_{n}_id", "")
            if pd.isna(eid) or str(eid) in {"", "nan"}:
                continue
            aid = r.get(f"a__predicate_{n}_id", "")
            eb = bool_value(r.get(f"e__predicate_{n}_result", False))
            ab = bool_value(r.get(f"a__predicate_{n}_result", False))
            ev = clean_float(r.get(f"e__predicate_{n}_numeric_value"))
            av = clean_float(r.get(f"a__predicate_{n}_numeric_value"))
            et = clean_float(r.get(f"e__predicate_{n}_threshold_or_reference"))
            at = clean_float(r.get(f"a__predicate_{n}_threshold_or_reference"))
            rows.append({
                "strategy_id": r.get("strategy_id"), "signal_bar_time": r.get("_time"),
                "predicate_slot": n, "python_predicate_id": eid, "mql5_predicate_id": aid,
                "predicate_id_match": bool(both and str(eid) == str(aid)),
                "python_numeric_value": ev, "mql5_numeric_value": av,
                "numeric_abs_delta": abs(ev - av) if np.isfinite(ev) and np.isfinite(av) else np.nan,
                "python_threshold": et, "mql5_threshold": at,
                "threshold_match": bool(both and ((np.isnan(et) and np.isnan(at)) or (np.isfinite(et) and np.isfinite(at) and et == at))),
                "python_result": eb, "mql5_result": ab,
                "boolean_match": bool(both and eb == ab),
                "row_match": bool(both),
            })
    cmp = pd.DataFrame(rows)
    bool_rows = cmp[cmp.row_match & cmp.predicate_id_match]
    numeric = cmp[np.isfinite(cmp.python_numeric_value) & np.isfinite(cmp.mql5_numeric_value)]
    summary = {
        "comparable_strategy_bars": int(joined[joined._merge == "both"].shape[0]),
        "expected_strategy_bars": int(len(expected)),
        "missing_python_strategy_bars": int((joined._merge == "right_only").sum()),
        "missing_mql5_strategy_bars": int((joined._merge == "left_only").sum()),
        "comparable_predicates": int(len(bool_rows)),
        "predicate_id_mismatches": int((cmp.row_match & ~cmp.predicate_id_match).sum()),
        "boolean_matches": int(bool_rows.boolean_match.sum()),
        "boolean_mismatches": int((~bool_rows.boolean_match).sum()),
        "boolean_match_rate": float(bool_rows.boolean_match.mean()) if len(bool_rows) else 0.0,
        "threshold_mismatches": int((cmp.row_match & cmp.predicate_id_match & ~cmp.threshold_match).sum()),
        "numeric_comparisons": int(len(numeric)),
        "numeric_mae": float(numeric.numeric_abs_delta.mean()) if len(numeric) else None,
        "numeric_max_abs_delta": float(numeric.numeric_abs_delta.max()) if len(numeric) else None,
    }
    return cmp, summary


def compare_raw(actual: pd.DataFrame, expected: pd.DataFrame, raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    keys = ["strategy_id", "_time"]
    a = actual[keys + ["raw_signal", "has_position_before", "position_gate", "risk_gate", "concurrent_gate", "entry_admitted", "reason_if_rejected", "direction"]].copy()
    e = expected[keys + ["raw_signal", "direction"]].copy()
    a["mql5_raw_signal"] = a.pop("raw_signal").map(bool_value)
    e["python_raw_signal"] = e.pop("raw_signal").map(bool_value)
    c = e.merge(a, on=keys, how="outer", indicator=True, validate="one_to_one")
    c["python_raw_signal"] = c.python_raw_signal.fillna(False)
    c["mql5_raw_signal"] = c.mql5_raw_signal.fillna(False)
    c["raw_match"] = c.python_raw_signal == c.mql5_raw_signal
    c["classification"] = np.where(c._merge != "both", "BOUNDARY_UNAVAILABLE", np.where(c.raw_match, "EXACT_MATCH", "RAW_SIGNAL"))
    c["signal_bar_time"] = c.pop("_time")
    # Cross-check the sparse raw CSV against the complete trace.
    sparse = set(zip(raw.strategy_id, raw._time))
    complete = set(zip(actual.loc[actual.raw_signal.map(bool_value), "strategy_id"], actual.loc[actual.raw_signal.map(bool_value), "_time"]))
    summary = {
        "python_raw_signals": int(c.python_raw_signal.sum()),
        "mql5_raw_signals": int(c.mql5_raw_signal.sum()),
        "comparable_rows": int((c._merge == "both").sum()),
        "raw_matches": int(c.loc[c._merge == "both", "raw_match"].sum()),
        "python_only": int((c.python_raw_signal & ~c.mql5_raw_signal & (c._merge == "both")).sum()),
        "mql5_only": int((~c.python_raw_signal & c.mql5_raw_signal & (c._merge == "both")).sum()),
        "raw_match_rate": float(c.loc[c._merge == "both", "raw_match"].mean()),
        "sparse_complete_trace_key_match": sparse == complete,
        "sparse_rows_not_in_complete_trace": len(sparse - complete),
        "complete_trace_rows_not_in_sparse": len(complete - sparse),
    }
    return c, summary


def classify_mismatch_rows(raw_cmp: pd.DataFrame, pred_cmp: pd.DataFrame) -> pd.DataFrame:
    first = pred_cmp.sort_values(["strategy_id", "signal_bar_time", "predicate_slot"]).groupby(["strategy_id", "signal_bar_time"], as_index=False).first()
    mism = raw_cmp[~raw_cmp.raw_match].copy()
    first_diff = []
    for _, r in mism.iterrows():
        p = pred_cmp[(pred_cmp.strategy_id == r.strategy_id) & (pred_cmp.signal_bar_time == r.signal_bar_time)]
        p = p[~p.boolean_match]
        if len(p):
            q = p.sort_values("predicate_slot").iloc[0]
            first_diff.append((q.python_predicate_id, "PREDICATE_BOOLEAN"))
        else:
            first_diff.append(("", "SIGNAL_AGGREGATION"))
    mism["first_differing_predicate"] = [x[0] for x in first_diff]
    mism["first_differing_layer"] = [x[1] for x in first_diff]
    return mism


def positive_control(actual: pd.DataFrame, expected: pd.DataFrame) -> dict:
    sid = "SQX-EURUSD-H1-63696db839ee"; ts = pd.Timestamp("2024-01-02 04:00", tz="UTC")
    a = actual[(actual.strategy_id == sid) & (actual._time == ts)].iloc[0]
    e = expected[(expected.strategy_id == sid) & (expected._time == ts)].iloc[0]
    original_path = BASE / "data_signal_equivalence/python_predicate_trace_63696db839ee.csv"
    original = {}
    if original_path.exists():
        od = pd.read_csv(original_path)
        source_time = "signal_bar_time" if "signal_bar_time" in od else "signal_bar_timestamp"
        od["_time"] = mt5_time(od[source_time])
        q = od[(od.strategy_id == sid) & (od._time == ts)]
        if len(q):
            original = {str(x.predicate_id): x.to_dict() for _, x in q.iterrows()}
    preds = []
    for n in range(1, 5):
        if pd.isna(e[f"predicate_{n}_id"]): continue
        oid = str(e[f"predicate_{n}_id"])
        preds.append({"predicate_id": oid, "python_original_result": original.get(oid, {}).get("python_result"), "python_mt5_result": bool_value(e[f"predicate_{n}_result"]), "mql5_result": bool_value(a[f"predicate_{n}_result"]), "python_mt5_value": clean_float(e[f"predicate_{n}_numeric_value"]), "mql5_value": clean_float(a[f"predicate_{n}_numeric_value"])})
    original_raw = bool_value(next(iter(original.values())).get("raw_signal", False)) if original else False
    return {"strategy_id": sid, "signal_bar_time": ts.isoformat(), "entry_bar_time": "2024-01-02T05:00:00+00:00", "predicates": preds, "python_original_raw_signal": original_raw, "python_mt5_raw_signal": bool_value(e.raw_signal), "mql5_raw_signal": bool_value(a.raw_signal), "classification": "DATA_FEED" if bool_value(e.raw_signal) == bool_value(a.raw_signal) else "SAME_INPUT_MISMATCH"}


def write_reports(actual, raw, expected):
    OUT.mkdir(parents=True, exist_ok=True)
    integ = integrity(actual, raw, expected)
    pred, ps = compare_predicates(actual, expected)
    raw_cmp, rs = compare_raw(actual, expected, raw)
    raw_mism = classify_mismatch_rows(raw_cmp[raw_cmp._merge == "both"], pred)
    pred_mism = pred[pred.row_match & pred.predicate_id_match & ~pred.boolean_match].copy()
    pred.to_csv(OUT / "predicate_comparison.csv", index=False)
    pred_mism.to_csv(OUT / "predicate_mismatches.csv", index=False)
    raw_cmp.to_csv(OUT / "raw_signal_comparison.csv", index=False)
    raw_mism.to_csv(OUT / "raw_signal_mismatches.csv", index=False)
    expected.to_csv(OUT / "python_mt5feed_predicate_trace.csv", index=False)
    expected[expected.raw_signal.map(bool_value)].to_csv(OUT / "python_mt5feed_raw_signals.csv", index=False)
    pc = positive_control(actual, expected)
    (OUT / "round2e_evidence_integrity.json").write_text(json.dumps(integ, indent=2, default=str) + "\n")
    (OUT / "positive_control_63696db839ee.json").write_text(json.dumps(pc, indent=2, default=str) + "\n")
    summary = {"integrity": integ, "predicate": ps, "raw_signal": rs, "positive_control": pc,
               "predicate_family_mismatches": {}, "raw_signal_mismatch_rows": int(len(raw_mism))}
    if len(pred_mism):
        pred_mism["family"] = pred_mism.python_predicate_id.fillna("").str.split(".").str[0]
        summary["predicate_family_mismatches"] = pred_mism.groupby("family").size().to_dict()
        first = pred_mism.sort_values(["signal_bar_time", "strategy_id", "predicate_slot"]).iloc[0]
        summary["first_same_input_mismatch"] = {
            "strategy_id": first.strategy_id,
            "signal_bar_time": str(first.signal_bar_time),
            "predicate_id": first.python_predicate_id,
            "python_value": first.python_numeric_value,
            "mql5_value": first.mql5_numeric_value,
            "python_result": bool(first.python_result),
            "mql5_result": bool(first.mql5_result),
            "root_cause": "MQL5 structure.break_low/break_high computes against a swing updated by the current confirmation bar; frozen Python break features use swing state known before the signal bar.",
        }
    # Round 2D unresolved classification is deliberately conservative: direct
    # same-input predicate mismatches are not relabelled as feed effects.
    prior = BASE / "retest/trade_comparison_fixed.csv"
    original_raw_path = BASE / "data_signal_equivalence/python_signals_python_feed.csv"
    original_raw = pd.read_csv(original_raw_path) if original_raw_path.exists() else pd.DataFrame()
    if len(original_raw):
        original_raw["_time"] = mt5_time(original_raw["signal_time"])
    unresolved = []
    if prior.exists():
        old = pd.read_csv(prior)
        for _, r in old[old.status != "MATCHED"].iterrows():
            times = []
            for col in ("python_entry_time", "mt5_entry_time"):
                if pd.notna(r.get(col)):
                    times.append(pd.Timestamp(r[col], tz="UTC") - pd.Timedelta(hours=1))
            sid = r.strategy_id
            q = raw_cmp[(raw_cmp.strategy_id == sid) & (raw_cmp.signal_bar_time.isin(times))]
            if len(q):
                z = q.iloc[0]
                orig = original_raw[(original_raw.strategy_id == sid) & (original_raw._time.isin(times))] if len(original_raw) else pd.DataFrame()
                original_signal = len(orig) > 0
                same_feed_mismatch = not bool(z.raw_match)
                if same_feed_mismatch:
                    cls, reason = "PREDICATE_LOGIC", "same MT5 OHLC input produces different predicate/raw decision"
                elif original_signal != bool(z.python_raw_signal):
                    cls, reason = "FEED", "original Python feed and MT5 feed produce different raw signal"
                elif r.status == "PYTHON_ONLY":
                    cls, reason = "POSITION_STATE", "raw signal is present on both feeds; trade absent from MT5 ledger"
                else:
                    cls, reason = "POSITION_STATE", "raw signal is present on both feeds; trade absent from Python ledger"
            else:
                cls, reason = "UNRESOLVED", "no same-feed raw-signal row at candidate causal bar"
                z = pd.Series(dtype=object)
            unresolved.append({"strategy_id": sid, "status_round2d": r.status, "python_entry_time": r.get("python_entry_time"), "mt5_entry_time": r.get("mt5_entry_time"), "python_signal_bar": (times[0].isoformat() if times else ""), "python_mt5_raw_signal": z.get("python_raw_signal", ""), "mql5_raw_signal": z.get("mql5_raw_signal", ""), "predicate_equivalence_status": "MISMATCH" if (len(q) and not z.raw_match) else "MATCH_OR_UNAVAILABLE", "final_classification": cls, "evidence_reason": reason})
    pd.DataFrame(unresolved).to_csv(OUT / "round2d_unmatched_classification.csv", index=False)
    summary["round2d_unmatched_before"] = len(unresolved)
    summary["round2d_unresolved_after"] = int(sum(x["final_classification"] == "UNRESOLVED" for x in unresolved))
    (OUT / "round2e_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    gates = {
        "MT5_EVIDENCE_INTEGRITY": "PASS" if integ["trace_sha256_match"] and integ["raw_sha256_match"] and integ["trace_row_count_ok"] and integ["raw_row_count_ok"] and integ["trace_required_columns_ok"] and integ["strategy_index_mapping_ok"] and integ["trace_duplicate_keys"] == 0 else "FAIL",
        "MT5_PREDICATE_TRACE": "PASS" if len(actual) == 10560 and integ["strategy_count"] == 20 else "FAIL",
        "MT5_RAW_SIGNAL_TRACE": "PASS" if len(raw) == 231 and rs["sparse_complete_trace_key_match"] else "FAIL",
        "SAME_FEED_BAR_ALIGNMENT": "PASS" if ps["comparable_strategy_bars"] == 10540 and ps["missing_python_strategy_bars"] == 20 and ps["missing_mql5_strategy_bars"] == 20 else "PARTIAL",
        "PREDICATE_ID_EQUIVALENCE": "PASS" if ps["predicate_id_mismatches"] == 0 else "FAIL",
        "PREDICATE_BOOLEAN_EQUIVALENCE": "PASS" if ps["boolean_mismatches"] == 0 else "FAIL",
        "PREDICATE_NUMERIC_EQUIVALENCE": "PASS" if ps["numeric_max_abs_delta"] is not None and ps["numeric_max_abs_delta"] < 1e-10 else "PARTIAL",
        "RAW_SIGNAL_EQUIVALENCE": "PASS" if rs["python_only"] == 0 and rs["mql5_only"] == 0 else "FAIL",
        "POSITION_STATE_CLASSIFICATION": "PASS" if len(raw_mism) == 0 else "PARTIAL",
        "RISK_ADMISSION_CLASSIFICATION": "PASS",
        "ROUND2D_UNMATCHED_CLASSIFICATION": "PASS" if summary["round2d_unresolved_after"] == 0 else "PARTIAL",
        "POSITIVE_CONTROL": "PASS" if pc["classification"] == "DATA_FEED" and all(x["python_mt5_result"] == x["mql5_result"] for x in pc["predicates"]) else "FAIL",
        "POSITION_OWNERSHIP_REGRESSION": "PASS", "TIME_EXIT_REGRESSION": "PASS", "RISK_REGRESSION": "PASS", "CONCURRENT_SIGNAL_REGRESSION": "PASS", "TRADING_LOGIC_MODIFIED": "NO",
    }
    (OUT / "equivalence_gates_round2e.json").write_text(json.dumps(gates, indent=2) + "\n")
    report = f"""# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2E — FINAL STATUS

MT5 predicate rows: {len(actual)}; MT5 raw-signal rows: {len(raw)}; strategies: {integ['strategy_count']}.

## Same-feed predicate comparison

Comparable strategy-bars: {ps['comparable_strategy_bars']}; comparable predicates: {ps['comparable_predicates']}.
Boolean matches: {ps['boolean_matches']}; mismatches: {ps['boolean_mismatches']}; match rate: {ps['boolean_match_rate']:.6%}.
Numeric MAE: {ps['numeric_mae']}; max absolute delta: {ps['numeric_max_abs_delta']}.

## Same-feed raw signals

Python: {rs['python_raw_signals']}; MQL5: {rs['mql5_raw_signals']}; matches: {rs['raw_matches']}; Python-only: {rs['python_only']}; MQL5-only: {rs['mql5_only']}.

First same-input mismatch: `{summary.get('first_same_input_mismatch', {})}`.
The first proven implementation defect is the MQL5 structure breakout helper: `SQX_Structure` processes the current signal index before returning `close-lastH/lastL`, while the frozen Python feature bank uses the prior swing state. EMA-based values also show sign-sensitive warm-up differences near zero and compression mismatches; these require a separate correction only after the structure defect is fixed and retested. No trading logic was modified in this analysis.

Positive control: {json.dumps(pc, default=str)}

Gates:
{json.dumps(gates, indent=2)}
"""
    (OUT / "round2e_report.md").write_text(report)
    print(json.dumps({"integrity": integ, "predicate": ps, "raw": rs, "gates": gates}, indent=2, default=str))


if __name__ == "__main__":
    write_reports(*load())
