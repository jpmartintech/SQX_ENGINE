import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_portfolio_factory_v3"

def test_v2_forensic_audit_detects_accounting_defect():
    d = json.loads((OUT / "portfolio_v2_forensic_audit.json").read_text())
    assert d["finding"] == "V2 substituted weighted individual metrics for a chronological portfolio path"
    assert d["maxdd_domain_violation"] is True

def test_golden_fixed_initial_accounting():
    d = json.loads((OUT / "economic_golden_tests.json").read_text())
    assert d["fixed_initial"]["final"] == 101000
    assert d["fixed_fractional"]["final"] == 100980

def test_genetic_portfolio_artifact_and_path_metrics():
    g = pd.read_parquet(OUT / "genetic_portfolios.parquet")
    assert len(g) >= 8000
    assert {"train_dd", "forward_dd", "forward"}.issubset(g.columns)
    assert (g.forward_dd >= 0).all()

def test_leverage_is_gated_after_portfolio_failure():
    d = json.loads((OUT / "leverage_cliff.json").read_text())
    assert d["activated"] is False if "activated" in d else d["classification"] == "NOT_EVALUATED"
    assert pd.read_parquet(OUT / "leverage_frontier.parquet").empty

def test_no_shadow_live_or_real_money():
    d = json.loads((OUT / "shadow_live_handoff.json").read_text())
    assert d["ready"] is False
    assert d["real_money_orders"] == "NONE"
