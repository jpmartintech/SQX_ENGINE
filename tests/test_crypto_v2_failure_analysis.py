import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.crypto_v2_failure_analysis import corr, slope


def test_temporal_slope_and_rank_correlation_are_deterministic():
    assert slope([1, 2, 3, 4]) == pytest.approx(1.0)
    assert slope([4, 3, 2, 1]) == pytest.approx(-1.0)
    assert corr([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)


def test_lockbox_invariant_after_failure_analysis():
    p = Path("runs/reports/crypto_v2_failure_analysis/README.md")
    if not p.exists():
        pytest.skip("failure analysis artifacts not present")
    d = json.loads(p.read_text())
    assert d["lockbox_access_before"] == 0
    assert d["lockbox_access_after"] == 0


def test_stored_oos_result_reproduction_is_exact():
    p = Path("runs/reports/crypto_v2_failure_analysis/portfolio_accounting_diagnostic.json")
    if not p.exists():
        pytest.skip("failure analysis artifacts not present")
    assert json.loads(p.read_text())["return_equivalence"] is True
