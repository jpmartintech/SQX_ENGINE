import pandas as pd
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("prop_v2_information_discovery", Path(__file__).parents[1] / "scripts/prop_v2_information_discovery.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
add_targets = _module.add_targets
market_features = _module.market_features


def test_market_features_are_closed_bar_only_and_timezone_stable():
    x = market_features("EURUSD")
    assert x.timestamp.is_monotonic_increasing
    assert "hour" in x and "session" in x
    assert x.timestamp.dt.tz is not None


def test_future_labels_do_not_change_causal_columns():
    rows = []
    for i, r in enumerate([1.0, -1.0, -1.0, 1.0, -1.0, 2.0]):
        t = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(hours=i)
        rows.append({"strategy_id": "s", "market": "EURUSD", "timeframe": "M15",
                     "direction": "LONG", "entry_timestamp": t, "exit_timestamp": t + pd.Timedelta(minutes=15),
                     "net_R": r, "exit_reason": "STOP" if r < 0 else "TARGET", "split": "DEVELOPMENT"})
    out = add_targets(pd.DataFrame(rows))
    assert pd.isna(out.iloc[-1].next5_R)
    assert out.iloc[0].prior_loss_streak == 0
    assert out.iloc[2].prior_loss_streak == 1
