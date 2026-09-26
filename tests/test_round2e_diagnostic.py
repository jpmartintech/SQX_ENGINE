from pathlib import Path
import json
import pandas as pd

from sqx_engine.deployment import MQL5Backend, PortfolioDefinition


def test_diagnostic_portfolio_defaults_off_and_preserves_causal_shift(tmp_path):
    p = PortfolioDefinition.from_sqlite("data/prop_portfolio_library.sqlite", "SQX-PROP-02760ECAC8BA")
    out = tmp_path / "portfolio.mq5"
    MQL5Backend().export_portfolio(p, out, include_dir=tmp_path / "Include/SQX")
    text = out.read_text()
    assert "input bool InpDiagnosticTrace=false" in text
    assert "InpDiagnosticFile=\"SQX_portfolio_predicate_trace.csv\"" in text
    assert "InpDiagnosticRawFile=\"SQX_portfolio_raw_signals.csv\"" in text
    assert text.count("SQX_TraceEvaluation(InpDiagnosticFile") == 20
    assert "r0[1].time" in text and "r0[0].time" in text
    assert "SQX_Trade.PositionClose(ticket)" in (tmp_path / "Include/SQX/sqx_execution.mqh").read_text()


def test_round2e_expected_trace_schema_and_membership():
    base = Path("runs/reports/deployment_engine_v1/portfolio_equivalence_round2/predicate_equivalence")
    schema = json.loads((base / "trace_schema.json").read_text())
    trace = pd.read_csv(base / "python_expected_predicate_trace_mt5_feed.csv")
    raw = pd.read_csv(base / "python_expected_raw_signals_mt5_feed.csv")
    assert schema["default_off"] is True
    assert schema["strategies"] == 20
    assert len(trace) == 10560
    assert len(raw) == 238
    assert trace.strategy_id.nunique() == 20
    assert set(trace["signal_bar_time"]) <= set(trace["evaluation_time"])
    assert trace["entry_bar_time"].notna().all()
