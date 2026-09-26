from pathlib import Path


def test_mt5_h1_diagnostic_is_non_trading_and_has_stable_schema():
    source = Path("deployments/mql5/tools/SQX_ExportH1Data.mq5").read_text()
    assert 'FileWrite(handle, "time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume")' in source
    assert "CopyRates(InpSymbol, InpTimeframe, InpFrom, InpTo, rates)" in source
    assert "FILE_WRITE | FILE_CSV | FILE_ANSI" in source
    assert "CTrade" not in source
    assert "OrderSend" not in source
    assert "PositionClose" not in source
    assert "SQX_DATA_EXPORT_DONE" in source
