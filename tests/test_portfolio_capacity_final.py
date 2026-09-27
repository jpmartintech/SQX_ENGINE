import json
from pathlib import Path

import pandas as pd

from importlib.machinery import SourceFileLoader

capacity = SourceFileLoader("portfolio_capacity_final_v1", "scripts/portfolio_capacity_final_v1.py").load_module()


def test_capacity_episode_partition_is_chronological_and_disjoint():
    starts = pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC")
    eps = pd.DataFrame({"index": range(20), "start": starts, "end": starts + pd.Timedelta(days=5), "horizon": 5})
    parts, non = capacity.split_episodes(eps)
    assert list(parts.loc[:parts.index[parts.split == "CALIBRATION"].min() - 1, "split"].unique()) == ["DEVELOPMENT"]
    assert set(parts.split) == {"DEVELOPMENT", "CALIBRATION", "VALIDATION"}
    assert parts.index[parts.split == "DEVELOPMENT"].max() < parts.index[parts.split == "CALIBRATION"].min()
    assert parts.index[parts.split == "CALIBRATION"].max() < parts.index[parts.split == "VALIDATION"].min()
    assert len(non) == 4


def test_capacity_frozen_manifest_has_requested_size_frontier():
    path = Path("runs/reports/prop_factory_v1_portfolio_capacity_final/frozen_candidate_manifest.json")
    data = json.loads(path.read_text())
    sizes = {row["size"] for row in data["candidates"]}
    assert {5, 10, 15, 20, 30, 40, 50}.issubset(sizes)
    assert data["count"] >= 14

