from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.features import prepare_features


ROOT = Path(__file__).resolve().parents[1]
MT5 = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2/data_signal_equivalence/mt5_h1_reference.csv"
INDICATORS = ROOT / "src/sqx_engine/deployment/templates.py"


def _data():
    d = pd.read_csv(MT5)
    d["timestamp"] = pd.to_datetime(d.time, format="%Y.%m.%d %H:%M:%S", utc=True)
    return d


def test_structure_fix_preserves_prior_swing_ordering_fixture():
    d = _data()
    features = prepare_features(d[["timestamp", "open", "high", "low", "close", "tick_volume"]].rename(columns={"tick_volume": "volume"}), grammar_version="v1.7")
    i = int(d.index[d.timestamp == pd.Timestamp("2024-01-02 02:00", tz="UTC")][0])
    assert np.isclose(features["structure.break_low.3"][i], -0.00043, atol=1e-10)
    source = INDICATORS.read_text()
    assert "beforeH=lastH;beforeL=lastL" in source
    assert "a[s].close-beforeL" in source
    assert "a[s].close-lastL" not in source


def test_mql5_ema_seed_matches_frozen_python_adjust_false():
    d = _data()
    close = d.close.to_numpy(float)
    n = 200
    target = int(d.index[d.timestamp == pd.Timestamp("2024-01-02 04:00", tz="UTC")][0])
    expected = pd.Series(close).ewm(span=n, adjust=False, min_periods=n).mean().iloc[target]
    # MQL5 series indexing: index zero is newest; the fixed helper seeds at
    # the oldest copied observation and recurses toward the requested shift.
    series = close[::-1]
    s = len(close) - 1 - target
    ema = series[-1]
    k = 2.0 / (n + 1.0)
    for j in range(len(series) - 2, s - 1, -1):
        ema = series[j] * k + ema * (1.0 - k)
    assert np.isclose(ema, expected, rtol=0, atol=1e-12)
    source = INDICATORS.read_text()
    assert "int z=ArraySize(a)-1" in source
    assert "int z=s+n*4" not in source


def test_common_runtime_preserves_ownership_and_diagnostic_contract():
    source = INDICATORS.read_text()
    assert "SQX_Structure" in source
    generated = (ROOT / "deployments/mql5/Experts/SQX/SQX_SQX_PROP_02760ECAC8BA.mq5").read_text()
    assert "InpDiagnosticTrace=false" in generated
    assert "SQX_Trade.PositionClose(ticket)" in (ROOT / "deployments/mql5/Include/SQX/sqx_execution.mqh").read_text()
    assert "SQX_LoadRates(_Symbol,SQX_S0_TF,r0,2000)" in generated


def test_compression_reconstructs_decimal_keltner_multiplier():
    source = INDICATORS.read_text()
    assert 'double multiplier=n>=6?StringToDouble(p[4]+"."+p[5]):StringToDouble(p[4])' in source
    assert 'StringToDouble(p[4])*q' not in source
