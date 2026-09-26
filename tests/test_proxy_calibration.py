import json
from pathlib import Path
from importlib.machinery import SourceFileLoader

import pandas as pd

calibration = SourceFileLoader("prop_proxy_calibration", "scripts/prop_proxy_calibration_v1.py").load_module()
canon, ranks = calibration.canon, calibration.ranks


def test_calibration_portfolio_identity_is_deterministic():
    a = canon(["b", "a"], .01, .02, "RANDOM")
    b = canon(["a", "b"], .01, .02, "RANDOM")
    assert a == b


def test_rank_metrics_and_funnel_are_recall_first():
    frame = pd.DataFrame({"portfolio_id":["a","b","c","d"], "proxy":[4.,3.,2.,1.], "exact":[1.,4.,3.,2.]})
    metrics = ranks(frame, "proxy", "exact")
    assert 0 <= metrics["top_20pct_overlap"] <= 1
    assert "spearman" in metrics and "kendall" in metrics


def test_calibration_artifact_contract_if_run():
    path = Path("runs/reports/prop_factory_v1_proxy_calibration/calibration_manifest.json")
    if not path.exists():
        return
    payload = json.loads(path.read_text())
    assert payload["sample"] > 0
    assert payload["authority"] == "BAR_EQUITY_REPLAY"
