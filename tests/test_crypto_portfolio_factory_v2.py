import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_portfolio_factory_v2"

def test_v2_asset_admission_is_explicit_and_venue_separated():
    d = json.loads((OUT / "asset_admission.json").read_text())
    assert d["portfolio_eligible"] == ["BTC", "ETH", "SOL", "XRP", "DOGE"]
    assert "Hyperliquid" not in d["assets"] if "assets" in d else True

def test_v2_factory_freezes_price_semantics():
    d = json.loads((OUT / "strategy_factory_freeze.json").read_text())
    assert d["grammar"] == "v1.7 PRICE_ONLY"
    assert d["changed_during_loop"] is False

def test_v2_burned_period_and_oos_firewall():
    d = json.loads((OUT / "oos_status.json").read_text())
    assert d["v11_final_oos_accesses"] == 1
    assert d["v2_new_virgin_oos_accesses"] == 0
    assert json.loads((OUT / "burned_2026_stress.json").read_text())["oos"] is False

def test_v2_leverage_requires_normalized_portfolio_gate():
    d = json.loads((OUT / "leverage_config.json").read_text())
    assert d["activated"] is False
    assert pd.read_parquet(OUT / "leverage_frontier.parquet").empty

def test_v2_terminal_classification_is_negative_and_no_live_orders():
    d = json.loads((OUT / "factory_summary.json").read_text())
    assert d["classification"] == "CRYPTO_PORTFOLIO_NOT_ROBUST"
    assert json.loads((OUT / "shadow_live_handoff.json").read_text())["ready"] is False
