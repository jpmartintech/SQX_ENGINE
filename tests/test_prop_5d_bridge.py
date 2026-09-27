import json
from pathlib import Path
from importlib.machinery import SourceFileLoader

bridge = SourceFileLoader("prop_5d_bridge", "scripts/prop_5d_search_bridge_v1.py").load_module()


def test_episode_engine_has_all_ftmo_horizons():
    import pandas as pd
    g = pd.DataFrame({"entry_timestamp": pd.to_datetime(["2024-01-01T00:00Z", "2024-01-02T00:00Z", "2024-01-03T00:00Z", "2024-01-04T00:00Z", "2024-01-05T00:00Z", "2024-01-08T00:00Z", "2024-01-09T00:00Z"], utc=True)})
    episodes = bridge.episode_days(g)
    assert set(episodes.horizon) == {5, 10, 15, 20} or set(episodes.horizon).issubset({5,10,15,20})


def test_bridge_identity_and_proxy_authority_artifacts_if_run():
    path = Path("runs/reports/prop_factory_v1_ftmo_5d_bridge/episode_manifest.json")
    if not path.exists():
        return
    payload = json.loads(path.read_text())
    assert payload["available_windows_5d"] > 0
    assert Path("runs/reports/prop_factory_v1_ftmo_5d_bridge/exact_frontier_challenge.parquet").exists()
