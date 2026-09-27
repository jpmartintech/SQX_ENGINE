"""Isolated PROP_V1 generation configuration.

The strategy canonical grammar remains V1.7.  This module only selects a
versioned subset of already implemented causal predicates and shorter exit
values; the General generator classes are not modified.
"""
from __future__ import annotations

from dataclasses import replace
import numpy as np

from ..generators.genetic import GeneticGenerator
from ..grammar import CATALOG

PROP_FACTORY_VERSION = "PROP_FACTORY_V1_PILOT"
PROP_FITNESS_VERSION = "PROP_FITNESS_V2_DOWNSIDE"
PROP_GRAMMAR_VERSION = "PROP_GRAMMAR_V1"
PROP_EXIT_VERSION = "PROP_EXIT_V3_STABLE_EXIT"
PROP_CANONICAL_GRAMMAR = "v1.7"
PROP_SURVIVOR_WIDTH = 0.30
PROP_EXIT_SPACE = {
    "stop_atr": (1.5, 2.0),
    "target_atr": (1.0, 1.5, 2.0),
    "time_exit_bars": (8, 12, 24),
    "atr_period": 14,
    "design_status": "PILOT_CONFIG_CALIBRATION_REQUIRED",
}


def prop_predicate_catalog():
    selected = {}
    for family, predicates in CATALOG.items():
        keep = []
        for predicate in predicates:
            feature = predicate.feature
            parts = feature.split(".")
            try:
                numeric = int(parts[-1])
            except ValueError:
                numeric = None
            allowed = True
            if feature.startswith("trend.ema_slope."):
                allowed = int(parts[2]) <= 50 and int(parts[3]) <= 6
            elif feature.startswith("trend.ema_pair.") or feature.startswith("trend.close_ema."):
                allowed = int(parts[2]) <= 50
            elif feature.startswith("trend.breakout_"):
                allowed = numeric is not None and numeric <= 20
            elif feature.startswith("momentum.roc.") or feature.startswith("momentum.willr."):
                allowed = numeric is not None and numeric <= 16
            elif feature.startswith("structure."):
                allowed = numeric is not None and numeric <= 3
            if allowed:
                keep.append(predicate)
        selected[family] = tuple(keep)
    return selected


class PropGeneticGenerator(GeneticGenerator):
    """Genetic generator with isolated predicate and exit sampling."""

    def __init__(self, *args, **kwargs):
        self.prop_catalog = prop_predicate_catalog()
        self.prop_predicates = tuple(p for values in self.prop_catalog.values() for p in values)
        super().__init__(*args, grammar_version=PROP_CANONICAL_GRAMMAR, **kwargs)

    def sample_predicate(self):
        return self.prop_predicates[int(self.rng.integers(len(self.prop_predicates)))]

    def _prop_exit(self, strategy):
        return replace(
            strategy,
            atr_period=PROP_EXIT_SPACE["atr_period"],
            stop_atr=float(self.rng.choice(PROP_EXIT_SPACE["stop_atr"])),
            target_atr=float(self.rng.choice(PROP_EXIT_SPACE["target_atr"])),
            time_exit=int(self.rng.choice(PROP_EXIT_SPACE["time_exit_bars"])),
            grammar_version=PROP_CANONICAL_GRAMMAR,
        )

    def ask(self, known_hashes=None):
        return self._prop_exit(super().ask(known_hashes=known_hashes))
