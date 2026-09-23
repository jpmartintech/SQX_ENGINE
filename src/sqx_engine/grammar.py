"""Finite V1.7 grammar. Grids are fixed ex ante, never fitted to market data."""
from collections import Counter
from math import comb

from .strategy import Predicate

FAMILIES = ('Trend', 'Momentum', 'Volatility', 'Structure')
EMA_PERIODS = (10, 20, 50, 100, 200)
SLOPE_HORIZONS = (1, 3, 6, 12)
BREAKOUT_PERIODS = (10, 20, 50, 100)
ROC_PERIODS = (4, 8, 16, 32)
ROC_THRESHOLDS = (-.005, 0., .005)  # fractional return, not percentage points
WILLR_PERIODS = (7, 14, 28)
FRACTAL_DEPTHS = (2, 3, 5)
STRUCTURES = {'HH': 1., 'HL': 2., 'LH': 3., 'LL': 4.}


def predicate_family(predicate):
    prefix = predicate.feature.split('.')[0]
    if prefix.title() in FAMILIES: return prefix.title()
    # Legacy columns retain their historical numeric semantics.
    if prefix.startswith('ema'): return 'Trend'
    if prefix.startswith(('rsi', 'adx')) or prefix == 'close': return 'Momentum'
    return 'Legacy'


def family_key(strategy):
    present = {predicate_family(p) for p in strategy.predicates}
    return '+'.join(f for f in (*FAMILIES, 'Legacy') if f in present)


def catalog():
    out = {f: [] for f in FAMILIES}
    def add(family, feature, values=(0.,), operators=('>', '<')):
        for value in values:
            for op in operators: out[family].append(Predicate(feature, op, value))
    for n in EMA_PERIODS:
        add('Trend', f'trend.close_ema.{n}')
        for k in SLOPE_HORIZONS: add('Trend', f'trend.ema_slope.{n}.{k}')
        for slow in EMA_PERIODS:
            if n < slow: add('Trend', f'trend.ema_pair.{n}.{slow}')
    for n in BREAKOUT_PERIODS:
        add('Trend', f'trend.breakout_high.{n}', operators=('>',))
        add('Trend', f'trend.breakout_low.{n}', operators=('<',))
    add('Momentum', 'rsi_14', (25., 30., 35., 40., 50., 60., 65., 70., 75.))
    for n in ROC_PERIODS: add('Momentum', f'momentum.roc.{n}', ROC_THRESHOLDS)
    for n in WILLR_PERIODS: add('Momentum', f'momentum.willr.{n}', (-80., -50., -20.))
    for n in (14, 28): add('Volatility', f'volatility.atr_regime.{n}.50')
    for n in (20, 50):
        add('Volatility', f'volatility.bb_upper.{n}.2', operators=('>',))
        add('Volatility', f'volatility.bb_lower.{n}.2', operators=('<',))
        add('Volatility', f'volatility.bb_middle.{n}.2')
        # 1 = both BB bands inside KC; -1 = both outside; 0 = mixed/boundary.
        add('Volatility', f'volatility.compression.{n}.2.1.5', (-1., 1.), ('==',))
    for d in FRACTAL_DEPTHS:
        add('Structure', f'structure.last.{d}', tuple(STRUCTURES.values()), ('==',))
        add('Structure', f'structure.break_high.{d}', operators=('>',))
        add('Structure', f'structure.break_low.{d}', operators=('<',))
        add('Structure', f'structure.fractal_high.{d}', (1.,), ('==',))
        add('Structure', f'structure.fractal_low.{d}', (1.,), ('==',))
    return {f: tuple(ps) for f, ps in out.items()}


CATALOG = catalog()
ALL_PREDICATES = tuple(p for ps in CATALOG.values() for p in ps)


def search_space(min_predicates=1, max_predicates=4):
    n = len(ALL_PREDICATES)
    compositions = n + sum(2 * comb(n, k) for k in range(max(2, min_predicates), max_predicates + 1)) if min_predicates == 1 else sum(2 * comb(n, k) for k in range(min_predicates, max_predicates + 1))
    return {'predicate_variants': n, 'by_family': {f: len(ps) for f, ps in CATALOG.items()},
            'exit_variants': 4 * 4 * 4, 'directions': 2, 'logic_variants': 2,
            'predicate_count_variants': list(range(min_predicates, max_predicates + 1)),
            'syntactic_upper_bound': compositions * 64 * 2,
            'note': 'Unique unordered predicates; single-predicate logic normalized. Includes contradictory/tautological combinations; not a count of distinct behaviors.'}


def count_stage(telemetry, stage, strategy):
    key = family_key(strategy)
    row = telemetry.setdefault(key, {})
    row[stage] = row.get(stage, 0) + 1


def family_totals(telemetry):
    generated = {key: row.get('GENERATED', 0) for key, row in telemetry.items()}
    return {'strategies_by_family': generated,
            'single_family': sum(n for key, n in generated.items() if '+' not in key),
            'multi_family': sum(n for key, n in generated.items() if '+' in key)}
