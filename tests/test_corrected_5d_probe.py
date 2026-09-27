import pandas as pd
from importlib.machinery import SourceFileLoader

probe = SourceFileLoader("corrected_5d_probe_v1", "scripts/corrected_5d_probe_v1.py").load_module()
all_episodes = probe.all_episodes
build_sample = probe.build_sample


def test_corrected_probe_builds_exactly_120_deterministic_portfolios():
    ids = [f"SQX-EURUSD-H1-{i:012x}" for i in range(200)]
    meta = pd.DataFrame({
        "strategy_id": ids,
        "trades": [i % 17 + 1 for i in range(len(ids))],
        "mean_R": [float(i % 11) / 100 for i in range(len(ids))],
        "markets": 1,
        "timeframes": 1,
        "direction": "LONG",
    })
    first = build_sample(ids, meta, seed=2601)
    second = build_sample(ids, meta, seed=2601)
    assert len(first) == 120
    assert first.portfolio_id.is_unique
    assert first.method.value_counts().to_dict() == {
        "RANDOM": 20,
        "CUMULATIVE_R_GREEDY": 20,
        "FIVE_DAY_RETURN_GREEDY": 20,
        "FREQUENCY_RISK_GREEDY": 20,
        "DIVERSITY_GREEDY": 20,
        "GENETIC_LOCAL": 20,
    }
    pd.testing.assert_frame_equal(first, second)


def test_corrected_probe_episode_inventory_uses_five_trading_days():
    timestamps = pd.date_range("2024-01-01", periods=8, freq="D", tz="UTC")
    events = pd.DataFrame({"entry_timestamp": timestamps})
    episodes = all_episodes(events)
    assert len(episodes) == 4
    assert (episodes.horizon == 5).all()
    assert episodes.iloc[0].start == pd.Timestamp("2024-01-01 00:00:00+0100")
    assert episodes.iloc[0].end > episodes.iloc[0].start
