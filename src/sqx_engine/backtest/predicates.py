"""Numeric predicate IR: (feature column index, operator code, threshold).

Both backends consume identical precomputed causal features. Numba dispatches
numeric comparisons inside its compiled loop, never Python dispatch per bar.
"""
import numpy as np
from .numba_core import NUMBA_AVAILABLE

OPERATOR_CODES = {'>': 1, '<': 2, '==': 3}


def python_predicate(values, code, threshold):
    if code == 1: mask = values > threshold
    elif code == 2: mask = values < threshold
    elif code == 3: mask = values == threshold
    else: raise ValueError('Unknown numeric predicate code')
    return mask & np.isfinite(values)


if NUMBA_AVAILABLE:
    from numba import njit

    @njit(cache=True)
    def numba_predicate(values, code, threshold):
        result = np.empty(len(values), dtype=np.bool_)
        for i in range(len(values)):
            x = values[i]
            if code == 1: result[i] = np.isfinite(x) and x > threshold
            elif code == 2: result[i] = np.isfinite(x) and x < threshold
            elif code == 3: result[i] = np.isfinite(x) and x == threshold
            else: raise ValueError('Unknown numeric predicate code')
        return result
else:
    numba_predicate = python_predicate
