import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/external_validation_lab_v1"

def test_protocol_frozen_before_strategy_access():
    m = json.loads((OUT / "EXPERIMENT_MANIFEST.json").read_text())
    assert m["protocol_frozen_before_strategy_evaluation"] is True
    assert m["strategy_factory_modified"] is False

def test_external_canonical_isolated_and_volume_not_signal():
    d = json.loads((OUT / "external_canonical_metadata.json").read_text())
    assert d["volume_used_as_signal"] is False
    assert "external_validation_lab_v1" in d["canonical_path"]

def test_reference_fast_equivalence():
    d = json.loads((OUT / "evaluator_equivalence.json").read_text())
    assert d["sample_size"] > 0
    assert d["all_equivalent"] is True

def test_holdout_and_access_firewall():
    d = json.loads((OUT / "access_log.json").read_text())
    assert d["EXTERNAL_BTC_STRATEGY_ACCESSES_E1"] > 0
    assert d["EXTERNAL_BTC_STRATEGY_ACCESSES_E2"] > 0
    assert d["EXTERNAL_BTC_STRATEGY_ACCESSES_X2"] == 0
    assert d["OTHER_EXTERNAL_CRYPTO_ACCESSES"] == 0

def test_fixed_controls_are_chronological_artifacts():
    d = pd.read_csv(OUT / "fixed_aggregate_controls.csv")
    assert {"E1", "E2", "X1_EXTERNAL", "X1_FUTURES"}.issubset(set(d.region))
    assert {"ALL_EQUAL", "TOP_N", "LONG_ONLY", "SHORT_ONLY"}.issubset(set(d.control))

def test_strategy_universe_is_frozen_btc_m15_price_only():
    d = pd.read_csv(OUT / "btc_m15_frozen_strategy_universe.csv")
    assert len(d) == 183
    assert set(d.asset) == {"BTC"}
    assert set(d.timeframe) == {"M15"}
    assert set(d.variant) == {"PRICE"}
