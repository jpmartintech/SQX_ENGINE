from pathlib import Path
import hashlib
import json
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2/predicate_equivalence"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_round2e_captured_evidence_integrity():
    integrity = json.loads((OUT / "round2e_evidence_integrity.json").read_text())
    assert integrity["trace_sha256_match"] is True
    assert integrity["raw_sha256_match"] is True
    assert integrity["trace_rows"] == 10560
    assert integrity["raw_rows"] == 231
    assert integrity["strategy_count"] == 20
    assert integrity["trace_duplicate_keys"] == 0
    assert integrity["positive_control_present"] is True


def test_round2e_comparator_preserves_same_input_mismatch_evidence():
    predicates = pd.read_csv(OUT / "predicate_comparison.csv")
    mismatches = predicates[(predicates["row_match"]) & (predicates["predicate_id_match"]) & (~predicates["boolean_match"])]
    assert len(mismatches) == 197
    first = mismatches.sort_values(["signal_bar_time", "strategy_id", "predicate_slot"]).iloc[0]
    assert first["strategy_id"] == "SQX-EURUSD-H1-a27691004dcc"
    assert first["python_predicate_id"] == "structure.break_low.3"
    assert first["signal_bar_time"].startswith("2024-01-02 02:00:00")


def test_round2e_positive_control_is_same_feed_equivalent():
    control = json.loads((OUT / "positive_control_63696db839ee.json").read_text())
    assert control["python_mt5_raw_signal"] is True
    assert control["mql5_raw_signal"] is True
    assert all(p["python_mt5_result"] == p["mql5_result"] for p in control["predicates"])
