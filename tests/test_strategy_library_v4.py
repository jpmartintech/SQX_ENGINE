import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/strategy_library_v4"

def test_temporal_artifacts_exist_and_are_causal_profiles():
    for name in ["temporal_edge_matrix_monthly.parquet", "temporal_edge_matrix_quarterly.parquet", "temporal_edge_matrix_6m.parquet", "strategy_edge_profiles.parquet"]:
        assert (OUT / name).exists()
    d = pd.read_parquet(OUT / "strategy_edge_profiles.parquet")
    assert {"positive_window_ratio", "active_window_ratio", "edge_state"}.issubset(d.columns)

def test_persistence_policy_is_explicit():
    d = json.loads((OUT / "library_policy_definitions.json").read_text())
    assert "PERSISTENT_EDGE" in d
    assert "RAW_EDGE" in d

def test_raw_vs_persistence_comparison_has_same_cycles():
    d = pd.read_parquet(OUT / "portfolio_walk_forward.parquet")
    assert len(d) == 4
    assert {"forward_return_raw", "forward_return_persistent"}.issubset(d.columns)

def test_no_future_oos_or_live_candidate():
    d = json.loads((OUT / "oos_status.json").read_text())
    assert d["new_virgin_oos"] == 0
    assert json.loads((OUT / "shadow_live_handoff.json").read_text())["ready"] is False

def test_leverage_not_reached_without_persistence_value():
    d = json.loads((OUT / "leverage_cliff.json").read_text())
    assert d["activated"] is False
