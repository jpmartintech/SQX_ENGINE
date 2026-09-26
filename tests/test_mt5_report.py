from pathlib import Path

from sqx_engine.deployment.mt5_report import parse_config, parse_report


REPORT = Path("runs/reports/deployment_engine_v1/full_mt5_oos/ReportTester_full_oos_2024_2026.html")


def test_mt5_report_tables_and_counts():
    parsed = parse_report(REPORT)
    assert len(parsed["orders"]) == 2962
    assert len(parsed["deals"]) == 2962
    assert parsed["deals"].direction.value_counts().to_dict() == {"in": 1481, "out": 1481}
    assert len(parsed["balance"]) == 1


def test_mt5_report_preserves_strategy_comments_and_deal_fields():
    parsed = parse_report(REPORT)
    orders = parsed["orders"]
    deals = parsed["deals"]
    assert orders.comment.str.startswith("SQX-").sum() == 1481
    assert deals.comment.str.startswith("SQX-").sum() == 1481
    assert parsed["balance"].balance.iloc[0] == 100000.0


def test_mt5_report_configuration_is_explicit():
    parsed = parse_report(REPORT)
    config = parse_config(parsed["text"])
    assert config["expert"] == "SQX_SQX_PROP_02760ECAC8BA"
    assert config["symbol"] == "EURUSD"
    assert config["period"] == "H1 (2024.01.01 - 2026.04.14)"
    assert config["base_risk"] == "0.01"
    assert config["max_open_risk"] == "0.02"
    assert config["diagnostic_trace"] == "false"

