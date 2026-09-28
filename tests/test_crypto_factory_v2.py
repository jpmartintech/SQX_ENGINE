import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.crypto_factory_v2 import Firewall, RATIOS, split_bounds


def frame(start="2020-01-01", periods=100):
    t = pd.date_range(start, periods=periods, freq="15min", tz="UTC")
    return pd.DataFrame({"timestamp": t, "open": 1.0, "high": 1.1, "low": .9, "close": 1.0, "volume": 1.0})


def test_ratio_policy_sums_to_one():
    assert sum(RATIOS.values()) == pytest.approx(1.0)


def test_elapsed_time_splits_are_monotonic_and_ratio_based():
    b = split_bounds(frame())
    assert b["START"] < b["DEV_END"] < b["VAL_END"] < b["OOS_END"] < b["END"]
    total = b["END"] - b["START"]
    assert (b["DEV_END"] - b["START"]) / total == pytest.approx(.60)
    assert (b["VAL_END"] - b["START"]) / total == pytest.approx(.75)


def test_firewall_rejects_protected_access_at_intake_and_wrong_stage():
    manifest = {"experiment_id": "t", "git_commit": "x", "stage": "DATA_INTAKE",
                "ratios": RATIOS, "DEV": {}, "bounds": {}}
    f = Firewall(manifest, [])
    with pytest.raises(PermissionError):
        f.access("BTC", "DEV", "test")
    manifest["stage"] = "DEV"
    with pytest.raises(PermissionError):
        f.access("BTC", "OOS", "test")


def test_firewall_allows_only_current_protected_stage_and_ledgers_access():
    ledger = []
    manifest = {"experiment_id": "t", "git_commit": "x", "stage": "DEV", "ratios": RATIOS,
                "BTC": {"bounds": {"START": "2020-01-01T00:00:00Z", "DEV_END": "2020-02-01T00:00:00Z", "VAL_END": "2020-03-01T00:00:00Z", "OOS_END": "2020-04-01T00:00:00Z", "END": "2020-05-01T00:00:00Z"}}}
    f = Firewall(manifest, ledger)
    f.access("BTC", "DEV", "test")
    assert ledger[0]["segment"] == "DEV"
    assert f.counts["DEV"] == 1


def test_completed_v2_run_keeps_lockbox_closed():
    p = Path("runs/reports/crypto_factory_v2/data_access_summary.json")
    if not p.exists():
        pytest.skip("V2 run not present")
    d = json.loads(p.read_text())
    assert d["lockbox_access_count"] == 0
