import numpy as np
from scripts.crypto_strategy_factory_v2 import max_streak, slope

def test_persistence_helpers_are_deterministic():
    assert max_streak([False, True, True, False, True]) == 2
    assert np.isclose(slope([1.0, 2.0, 3.0]), 1.0)

def test_persistence_slope_handles_short_input():
    assert np.isnan(slope([1.0]))
