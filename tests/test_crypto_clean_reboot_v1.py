import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from crypto_clean_reboot_v1 import _fast_nonoverlap

def test_fast_nonoverlap_basic_loss_and_win():
    close=np.array([100.,99.,101.])
    out=_fast_nonoverlap(np.array([0,2]),np.array([1,2]),np.array([1,1]),np.array([-1.,1.]),np.array([100.,99.]),np.array([99.,101.]),close,.01)
    assert out[6] == 2
    assert out[0] < 0

def test_fast_engine_is_deterministic():
    args=(np.array([0]),np.array([1]),np.array([1]),np.array([-1.]),np.array([100.]),np.array([99.]),np.array([100.,99.]),.01)
    assert np.allclose(_fast_nonoverlap(*args), _fast_nonoverlap(*args))
