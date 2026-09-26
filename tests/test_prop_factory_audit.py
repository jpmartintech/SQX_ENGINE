import json
from pathlib import Path

import pandas as pd

from sqx_engine.portfolio_factory.ftmo_v2 import Ftmo2StepProfile
from sqx_engine.prop_factory.audit import _oracle, _rolling_windows


def test_ftmo_product_modes_are_explicit_and_separate():
    profile = Ftmo2StepProfile()
    assert profile.name == "FTMO_2STEP_V1"
    assert profile.challenge_target == .10
    assert profile.verification_target == .05
    assert profile.timezone == "Europe/Paris"


def test_five_day_windows_and_oracle_are_diagnostic_not_tradable():
    trades = pd.DataFrame([
        {"strategy_id":"a", "market":"EURUSD", "timeframe":"H1", "direction":"LONG", "entry_timestamp":"2024-01-01T09:00Z", "net_R":2.0},
        {"strategy_id":"b", "market":"GBPUSD", "timeframe":"M15", "direction":"SHORT", "entry_timestamp":"2024-01-02T09:00Z", "net_R":-1.0},
        {"strategy_id":"c", "market":"USDJPY", "timeframe":"H4", "direction":"LONG", "entry_timestamp":"2024-01-08T09:00Z", "net_R":3.0},
    ])
    windows = _rolling_windows(trades)
    assert "rolling_5d_signals" in windows
    oracle = _oracle(windows, trades)
    assert {"oracle_a_R", "oracle_b_R", "oracle_c_R"}.issubset(oracle.columns)
    assert oracle.oracle_c_R.max() <= 3.0


def test_factory_artifact_contract_if_audit_has_run():
    path = Path("runs/reports/prop_factory_v1_ftmo_audit/prop_ready_universe.json")
    if not path.exists():
        return
    payload = json.loads(path.read_text())
    assert payload["total"] == 8438
    assert payload["prop_ready"] == 8438
