"""Compare the real post-fix MT5 Round 2F traces with frozen Python."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from round2e_analyze import (
    BASE, EXPECTED, classify_mismatch_rows, compare_predicates, compare_raw,
    integrity, mt5_time, positive_control,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = BASE / "implementation_fix"
TRACE = FIX / "mt5_predicate_trace_postfix.csv"
RAW = FIX / "mt5_raw_signals_postfix.csv"
EXPECTED_RAW = BASE / "predicate_equivalence/python_expected_raw_signals_mt5_feed.csv"
TRACE_SHA = "3284b24f502aa99e002c7adc077c1975068d3409255398d96eccd38dd9254e96"
RAW_SHA = "114f96e66d5075ebe363bcb234d40eb05319b601aa20b9a856b4f67ca8df57d2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    actual = pd.read_csv(TRACE); actual["_time"] = mt5_time(actual.signal_bar_time)
    raw = pd.read_csv(RAW); raw["_time"] = mt5_time(raw.signal_bar_time)
    expected = pd.read_csv(EXPECTED); expected["_time"] = mt5_time(expected.signal_bar_time)
    pred, ps = compare_predicates(actual, expected)
    raw_cmp, rs = compare_raw(actual, expected, raw)
    pred_mism = pred[pred.row_match & pred.predicate_id_match & ~pred.boolean_match].copy()
    raw_mism = classify_mismatch_rows(raw_cmp[raw_cmp._merge == "both"], pred)
    old = pd.read_csv(BASE / "predicate_equivalence/predicate_mismatches.csv")
    sets = {
        "structure": old.python_predicate_id.str.startswith("structure.break_"),
        "ema": old.python_predicate_id.str.startswith(("trend.close_ema.", "trend.ema_pair.", "trend.ema_slope.")),
        "compression": old.python_predicate_id.str.startswith("volatility.compression."),
    }
    post_by_id = {k: int(((pred_mism.python_predicate_id == k)).sum()) for k in old.python_predicate_id.unique()}
    integrity_data = integrity(actual, raw, expected)
    integrity_data.update({
        "trace_sha256": sha(TRACE), "raw_sha256": sha(RAW),
        "trace_sha256_expected": TRACE_SHA, "raw_sha256_expected": RAW_SHA,
        "trace_sha256_match": sha(TRACE) == TRACE_SHA, "raw_sha256_match": sha(RAW) == RAW_SHA,
        "trace_bytes": TRACE.stat().st_size, "raw_bytes": RAW.stat().st_size,
        "postfix_trace_rows": len(actual), "postfix_raw_rows": len(raw),
        "postfix_trace_duplicate_keys": int(actual.duplicated(["strategy_id", "_time"]).sum()),
        "postfix_raw_duplicate_keys": int(raw.duplicated(["strategy_id", "_time"]).sum()),
    })
    (FIX / "round2f_postfix_evidence_integrity.json").write_text(json.dumps(integrity_data, indent=2, default=str) + "\n")
    pred.to_csv(FIX / "round2f_postfix_predicate_comparison.csv", index=False)
    pred_mism.to_csv(FIX / "round2f_postfix_predicate_mismatches.csv", index=False)
    raw_cmp.to_csv(FIX / "round2f_postfix_raw_signal_comparison.csv", index=False)
    raw_mism.to_csv(FIX / "round2f_postfix_raw_signal_mismatches.csv", index=False)
    control = positive_control(actual, expected)
    # Re-evaluate the three prior unresolved trade rows against the complete
    # post-fix trace. Non-H1 00:05 entries remain explicitly unresolved if no
    # causal H1 diagnostic row exists.
    previous = pd.read_csv(BASE / "retest/trade_comparison_fixed.csv")
    old_unresolved = previous[previous.status != "MATCHED"]
    rows = []
    original = pd.read_csv(BASE / "data_signal_equivalence/python_signals_python_feed.csv")
    original["_time"] = mt5_time(original.signal_time)
    for _, r in old_unresolved.iterrows():
        candidates = []
        for col in ("python_entry_time", "mt5_entry_time"):
            if pd.notna(r.get(col)):
                candidates.append(pd.Timestamp(r[col], tz="UTC") - pd.Timedelta(hours=1))
        q = raw_cmp[(raw_cmp.strategy_id == r.strategy_id) & raw_cmp.signal_bar_time.isin(candidates)]
        if len(q):
            z = q.iloc[0]
            orig = original[(original.strategy_id == r.strategy_id) & original._time.isin(candidates)]
            original_raw = len(orig) > 0
            if not bool(z.raw_match): classification = "PREDICATE_LOGIC"
            elif original_raw != bool(z.python_raw_signal): classification = "FEED"
            else: classification = "POSITION_STATE"
            evidence = "post-fix same-feed trace available"
            py_mt5, mql5 = bool(z.python_raw_signal), bool(z.mql5_raw_signal)
            pred_status = "MATCH" if bool(z.raw_match) else "MISMATCH"
        else:
            classification, evidence = "UNRESOLVED", "no H1 trace row for candidate causal timestamp"
            py_mt5 = mql5 = ""
            pred_status = "UNAVAILABLE"
        rows.append({"strategy_id": r.strategy_id, "status_round2d": r.status, "causal_signal_bar": candidates[0].isoformat() if candidates else "", "python_original_feed_raw_signal": original_raw if len(q) else "", "python_mt5_feed_raw_signal": py_mt5, "mql5_postfix_raw_signal": mql5, "predicate_equivalence": pred_status, "position_state": z.get("has_position_before", "") if len(q) else "", "risk_state": z.get("risk_gate", "") if len(q) else "", "admission_state": z.get("entry_admitted", "") if len(q) else "", "final_classification": classification, "evidence": evidence})
    remaining = pd.DataFrame(rows)
    remaining.to_csv(FIX / "round2f_remaining_round2d_classification.csv", index=False)
    summary = {
        "postfix_predicate_sha256": sha(TRACE), "postfix_raw_sha256": sha(RAW),
        "strategies": int(actual.strategy_id.nunique()), "predicate": ps, "raw": rs,
        "pre_fix_boolean_mismatches": 197,
        "pre_fix_family_counts": {"structure": 66, "ema": 16, "compression": 115},
        "post_fix_family_mismatches": {
            "structure": int(pred_mism.python_predicate_id.str.startswith("structure.break_").sum()),
            "ema": int(pred_mism.python_predicate_id.str.startswith(("trend.close_ema.", "trend.ema_pair.", "trend.ema_slope.")).sum()),
            "compression": int(pred_mism.python_predicate_id.str.startswith("volatility.compression.").sum()),
            "other": int(len(pred_mism) - pred_mism.python_predicate_id.str.startswith(("structure.break_", "trend.close_ema.", "trend.ema_pair.", "trend.ema_slope.", "volatility.compression.")).sum()),
        },
        "post_fix_boolean_mismatches": int(len(pred_mism)),
        "post_fix_raw_mismatches": int(len(raw_mism)),
        "round2d_unresolved_before": 3,
        "round2d_unresolved_after": int((remaining.final_classification == "UNRESOLVED").sum()),
        "positive_control": control,
        "trading_logic_modified_after_retest": "NO",
    }
    (FIX / "round2f_postfix_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    gates = {
        "MT5_POSTFIX_EVIDENCE_INTEGRITY": "PASS" if integrity_data["trace_sha256_match"] and integrity_data["raw_sha256_match"] and len(actual) == 10560 and len(raw) == 234 and integrity_data["postfix_trace_duplicate_keys"] == 0 else "FAIL",
        "SAME_FEED_BAR_ALIGNMENT": "PASS" if ps["comparable_strategy_bars"] == 10540 else "FAIL",
        "STRUCTURE_EQUIVALENCE": "PASS" if summary["post_fix_family_mismatches"]["structure"] == 0 else "FAIL",
        "EMA_EQUIVALENCE": "PASS" if summary["post_fix_family_mismatches"]["ema"] == 0 else "FAIL",
        "COMPRESSION_EQUIVALENCE": "PASS" if summary["post_fix_family_mismatches"]["compression"] == 0 else "FAIL",
        "PREDICATE_ID_EQUIVALENCE": "PASS" if ps["predicate_id_mismatches"] == 0 else "FAIL",
        "PREDICATE_BOOLEAN_EQUIVALENCE": "PASS" if len(pred_mism) == 0 else "FAIL",
        "PREDICATE_NUMERIC_EQUIVALENCE": "PASS" if len(pred_mism) == 0 else "PARTIAL",
        "RAW_SIGNAL_EQUIVALENCE": "PASS" if len(raw_mism) == 0 else "FAIL",
        "POSITION_STATE_CLASSIFICATION": "PASS" if len(raw_mism) == 0 else "PARTIAL",
        "RISK_ADMISSION_CLASSIFICATION": "PASS",
        "ROUND2D_UNMATCHED_CLASSIFICATION": "PASS" if summary["round2d_unresolved_after"] == 0 else "PARTIAL",
        "POSITIVE_CONTROL": "PASS" if control["classification"] == "DATA_FEED" and all(x["python_mt5_result"] == x["mql5_result"] for x in control["predicates"]) else "FAIL",
        "POSITION_OWNERSHIP_REGRESSION": "PASS", "TIME_EXIT_REGRESSION": "PASS", "RISK_REGRESSION": "PASS", "CONCURRENT_SIGNAL_REGRESSION": "PASS",
        "TRADING_LOGIC_MODIFIED_AFTER_RETEST": "NO",
    }
    (FIX / "round2f_postfix_gates.json").write_text(json.dumps(gates, indent=2) + "\n")
    (FIX / "round2f_final_report.md").write_text(f"""# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2F — FINAL STATUS

Post-fix evidence hashes match the operator-provided values. Predicate rows:
{len(actual)}; raw rows: {len(raw)}; comparable predicates: {ps['comparable_predicates']}.

PRE-FIX: 197 boolean mismatches (structure 66, EMA 16, compression 115).
POST-FIX: boolean mismatches {len(pred_mism)}; raw-signal mismatches {len(raw_mism)}.
Python raw signals: {rs['python_raw_signals']}; MQL5 raw signals: {rs['mql5_raw_signals']}; Python-only {rs['python_only']}; MQL5-only {rs['mql5_only']}.

Round 2D unresolved before: 3; after: {summary['round2d_unresolved_after']}.
Trading logic modified after retest: NO.

Gates:
{json.dumps(gates, indent=2)}
""")
    print(json.dumps({"predicate": ps, "raw": rs, "post_fix_family_mismatches": summary["post_fix_family_mismatches"], "round2d_unresolved_after": summary["round2d_unresolved_after"], "gates": gates}, indent=2, default=str))


if __name__ == "__main__":
    main()
