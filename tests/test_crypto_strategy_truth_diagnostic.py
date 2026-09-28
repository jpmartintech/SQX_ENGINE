import numpy as np

from scripts.crypto_strategy_truth_diagnostic import spearman_local


def test_local_spearman_is_deterministic_without_scipy():
    assert spearman_local([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman_local([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0


def test_local_spearman_handles_ties_and_constant_series():
    value = spearman_local([1, 1, 2, 3], [3, 2, 2, 1])
    assert np.isfinite(value)
    assert spearman_local([1, 1], [2, 3]) == 0.0
