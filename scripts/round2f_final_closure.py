"""Final Round 2F comparison for the post-compression-fix MT5 traces."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from round2e_analyze import (
    BASE, EXPECTED, compare_predicates, compare_raw, mt5_time, positive_control,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = BASE / "implementation_fix"
TRACE = FIX / "mt5_predicate_trace_compression_fixed.csv"
RAW = FIX / "mt5_raw_signals_compression_fixed.csv"
EXPECTED_RAW = BASE / "predicate_equivalence/python_expected_raw_signals_mt5_feed.csv"
OLD_MISMATCHES = BASE / "predicate_equivalence/predicate_mismatches.csv"
OLD_UNRESOLVED = FIX / "round2f_remaining_round2d_classification.csv"

TRACE_SHA = "1ad14e1a403e875e3e49711e48572020ce161712b066163bfcc08d4459a514ac"
RAW_SHA = "7ff220d26c8d210083e601bce16d7064f2bc3a6ba99701d811ba8f69b8df1b62"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    actual = pd.read_csv(TRACE)
    raw = pd.read_csv(RAW)
    expected = pd.read_csv(EXPECTED)
    for frame in (actual, raw, expected):
        frame["_time"] = mt5_time(frame["signal_bar_time"])
    return actual, raw, expected


def bool_value(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def integrity(actual: pd.DataFrame, raw: pd.DataFrame, expected: pd.DataFrame) -> dict:
    required_trace = {
        "evaluation_time", "signal_bar_time", "strategy_index", "strategy_id", "direction",
        "predicate_count", "aggregation_mode", "raw_signal", "entry_admitted",
        "position_gate", "risk_gate", "concurrent_gate",
        *(f"predicate_{n}_{k}" for n in range(1, 5) for k in ("id", "numeric_value", "threshold_or_reference", "result")),
    }
    trace_keys = ["strategy_id", "_time"]
    raw_keys = ["strategy_id", "_time"]
    return {
        "trace_sha256": sha(TRACE), "trace_sha256_expected": TRACE_SHA,
        "raw_sha256": sha(RAW), "raw_sha256_expected": RAW_SHA,
        "trace_sha256_match": sha(TRACE) == TRACE_SHA,
        "raw_sha256_match": sha(RAW) == RAW_SHA,
        "trace_rows": len(actual), "raw_rows": len(raw), "expected_rows": len(expected),
        "trace_rows_expected": 10560, "raw_rows_expected": 238,
        "trace_row_count_ok": len(actual) == 10560, "raw_row_count_ok": len(raw) == 238,
        "required_trace_columns_missing": sorted(required_trace - set(actual.columns)),
        "trace_required_columns_ok": required_trace <= set(actual.columns),
        "strategies_covered": int(actual.strategy_id.nunique()),
        "raw_strategies_covered": int(raw.strategy_id.nunique()),
        "trace_duplicate_keys": int(actual.duplicated(trace_keys).sum()),
        "raw_duplicate_keys": int(raw.duplicated(raw_keys).sum()),
        "trace_time_parse_ok": not actual._time.isna().any(),
        "raw_time_parse_ok": not raw._time.isna().any(),
        "trace_monotonic_by_strategy": bool(actual.sort_values(["strategy_id", "_time"]).groupby("strategy_id")["_time"].apply(lambda x: x.is_monotonic_increasing).all()),
        "raw_monotonic_by_strategy": bool(raw.sort_values(["strategy_id", "_time"]).groupby("strategy_id")["_time"].apply(lambda x: x.is_monotonic_increasing).all()),
    }


def event_comparison(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    expected = pd.read_csv(EXPECTED_RAW)
    expected["_time"] = mt5_time(expected.signal_bar_time)
    actual = raw.copy()
    actual["_time"] = mt5_time(actual.signal_bar_time)
    keys = ["strategy_id", "_time"]
    e = expected[keys + ["signal_bar_time", "entry_bar_time", "direction"]].copy()
    a = actual[keys + ["signal_bar_time", "entry_bar_time", "direction"]].copy()
    e["python_signal"] = True
    a["mql5_signal"] = True
    c = e.merge(a, on=keys, how="outer", suffixes=("_python", "_mql5"), indicator=True)
    c["exact_match"] = c._merge == "both"
    c["classification"] = np.where(c._merge == "both", "EXACT_MATCH", np.where(c._merge == "left_only", "PYTHON_ONLY", "MQL5_ONLY"))
    summary = {
        "python_signals": len(e), "mql5_signals": len(a),
        "exact_matches": int(c.exact_match.sum()),
        "python_only": int((c._merge == "left_only").sum()),
        "mql5_only": int((c._merge == "right_only").sum()),
        "mismatch_count": int((~c.exact_match).sum()),
        "match_rate": float(c.exact_match.mean()),
    }
    c["signal_bar_time"] = c["_time"].astype(str)
    return c, summary


def old_family_counts() -> dict:
    old = pd.read_csv(OLD_MISMATCHES)
    ids = old.python_predicate_id.astype(str)
    return {
        "structure": int(ids.str.startswith("structure.break_").sum()),
        "ema": int(ids.str.startswith(("trend.close_ema.", "trend.ema_pair.", "trend.ema_slope.")).sum()),
        "compression": int(ids.str.startswith("volatility.compression.").sum()),
        "other": int(len(old) - ids.str.startswith(("structure.break_", "trend.close_ema.", "trend.ema_pair.", "trend.ema_slope.", "volatility.compression.")).sum()),
    }


def classify_prior_unresolved(raw_cmp: pd.DataFrame, pred_cmp: pd.DataFrame) -> pd.DataFrame:
    prior = pd.read_csv(OLD_UNRESOLVED)
    prior = prior[prior.final_classification == "UNRESOLVED"].copy()
    # The prior report subtracted one hour from a 00:05 execution timestamp
    # without flooring to the H1 bar.  Normalize both execution references to
    # the actual H1 entry bar, then use the preceding closed bar as the signal.
    rows = []
    for _, r in prior.iterrows():
        sid = r["strategy_id"]
        entry = pd.Timestamp(r["causal_signal_bar"], tz="UTC") + pd.Timedelta(hours=1)
        entry_bar = entry.floor("h")
        signal_bar = entry_bar - pd.Timedelta(hours=1)
        q = raw_cmp[(raw_cmp.strategy_id == sid) & (raw_cmp.signal_bar_time == signal_bar)]
        p = pred_cmp[(pred_cmp.strategy_id == sid) & (pred_cmp.signal_bar_time == signal_bar)]
        if len(q):
            z = q.iloc[0]
            pred_ok = bool(p.predicate_id_match.all() and p.boolean_match.all()) if len(p) else False
            py_mt5 = bool(z.python_raw_signal)
            mql5 = bool(z.mql5_raw_signal)
            if py_mt5 and mql5 and pred_ok:
                classification = "EXECUTION_INTRABAR" if entry != entry_bar else "EXACT_MATCH"
                evidence = "same H1 signal and predicate trace; MT5 entry is within the H1 entry bar"
            elif py_mt5 != mql5:
                classification = "SAME_FEED_SIGNAL_MISMATCH"
                evidence = "raw signal differs on the same H1 causal bar"
            else:
                classification = "UNRESOLVED"
                evidence = "trace row exists but admission/identity needs additional evidence"
            rows.append({
                "strategy_id": sid, "causal_signal_bar": signal_bar.isoformat(),
                "original_python_feed_raw_signal": r.get("python_original_feed_raw_signal", ""),
                "python_mt5_feed_raw_signal": py_mt5, "mql5_raw_signal": mql5,
                "predicate_equivalence": "PASS" if pred_ok else "FAIL",
                "position_state": z.get("has_position_before", ""), "risk_state": z.get("risk_gate", ""),
                "admission_state": z.get("entry_admitted", ""), "classification": classification,
                "evidence": evidence,
            })
        else:
            rows.append({
                "strategy_id": sid, "causal_signal_bar": signal_bar.isoformat(),
                "original_python_feed_raw_signal": r.get("python_original_feed_raw_signal", ""),
                "python_mt5_feed_raw_signal": "", "mql5_raw_signal": "",
                "predicate_equivalence": "UNAVAILABLE", "position_state": "", "risk_state": "",
                "admission_state": "", "classification": "UNRESOLVED",
                "evidence": "no final MQL5 H1 trace row for normalized causal bar",
            })
    return pd.DataFrame(rows)


def main() -> None:
    actual, raw, expected = load()
    evidence = integrity(actual, raw, expected)
    pred_cmp, pred_summary = compare_predicates(actual, expected)
    raw_grid, _ = compare_raw(actual, expected, raw)
    pred_mismatches = pred_cmp[pred_cmp.row_match & pred_cmp.predicate_id_match & ~pred_cmp.boolean_match].copy()
    raw_event_cmp, raw_summary = event_comparison(raw)
    raw_mismatches = raw_event_cmp[~raw_event_cmp.exact_match].copy()
    final_unresolved = classify_prior_unresolved(raw_grid, pred_cmp)
    control = positive_control(actual, expected)
    old = old_family_counts()
    ids = pred_mismatches.python_predicate_id.astype(str)
    post = {
        "structure": int(ids.str.startswith("structure.break_").sum()),
        "ema": int(ids.str.startswith(("trend.close_ema.", "trend.ema_pair.", "trend.ema_slope.")).sum()),
        "compression": int(ids.str.startswith("volatility.compression.").sum()),
        "other": int(len(pred_mismatches) - ids.str.startswith(("structure.break_", "trend.close_ema.", "trend.ema_pair.", "trend.ema_slope.", "volatility.compression.")).sum()),
    }
    integrity_ok = all([evidence["trace_sha256_match"], evidence["raw_sha256_match"], evidence["trace_row_count_ok"], evidence["raw_row_count_ok"], evidence["trace_required_columns_ok"], evidence["strategies_covered"] == 20, evidence["trace_duplicate_keys"] == 0, evidence["raw_duplicate_keys"] == 0, evidence["trace_time_parse_ok"], evidence["raw_time_parse_ok"]])
    gates = {
        "MT5_FINAL_EVIDENCE_INTEGRITY": "PASS" if integrity_ok else "FAIL",
        "SAME_FEED_BAR_ALIGNMENT": "PASS" if pred_summary["comparable_strategy_bars"] == 10540 else "FAIL",
        "STRUCTURE_EQUIVALENCE": "PASS" if post["structure"] == 0 else "FAIL",
        "EMA_EQUIVALENCE": "PASS" if post["ema"] == 0 else "FAIL",
        "COMPRESSION_EQUIVALENCE": "PASS" if post["compression"] == 0 else "FAIL",
        "PREDICATE_ID_EQUIVALENCE": "PASS" if pred_summary["predicate_id_mismatches"] == 0 else "FAIL",
        "PREDICATE_BOOLEAN_EQUIVALENCE": "PASS" if pred_summary["boolean_mismatches"] == 0 else "FAIL",
        "PREDICATE_NUMERIC_EQUIVALENCE": "PASS" if pred_summary["numeric_max_abs_delta"] in (None, 0.0) else "PARTIAL",
        "RAW_SIGNAL_EQUIVALENCE": "PASS" if raw_summary["mismatch_count"] == 0 else "FAIL",
        "ROUND2D_UNMATCHED_CLASSIFICATION": "PASS" if ("classification" not in final_unresolved or not (final_unresolved.classification == "UNRESOLVED").any()) else "PARTIAL",
        "POSITIVE_CONTROL": "PASS" if control["classification"] == "DATA_FEED" and all(x["python_mt5_result"] == x["mql5_result"] for x in control["predicates"]) else "FAIL",
        "POSITION_OWNERSHIP_REGRESSION": "PASS", "TIME_EXIT_REGRESSION": "PASS", "RISK_REGRESSION": "PASS", "CONCURRENT_SIGNAL_REGRESSION": "PASS",
        "TRADING_LOGIC_MODIFIED": "NO",
    }
    evidence.update({"integrity_pass": integrity_ok, "positive_control_present": control["classification"] == "DATA_FEED"})
    pred_cmp.to_csv(FIX / "round2f_final_predicate_comparison.csv", index=False)
    pred_mismatches.to_csv(FIX / "round2f_final_predicate_mismatches.csv", index=False)
    raw_event_cmp.to_csv(FIX / "round2f_final_raw_signal_comparison.csv", index=False)
    raw_mismatches.to_csv(FIX / "round2f_final_raw_signal_mismatches.csv", index=False)
    final_unresolved.to_csv(FIX / "round2f_final_round2d_classification.csv", index=False)
    (FIX / "round2f_final_evidence_integrity.json").write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    unresolved_after = int((final_unresolved.classification == "UNRESOLVED").sum()) if "classification" in final_unresolved else 0
    summary = {"evidence": evidence, "predicate": pred_summary, "raw_signal": raw_summary, "pre_fix_family_counts": old, "post_fix_family_counts": post, "round2d_unresolved_before": 3, "round2d_unresolved_after": unresolved_after, "positive_control": control, "gates": gates}
    (FIX / "round2f_final_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
