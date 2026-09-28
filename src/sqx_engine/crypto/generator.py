"""Deterministic Crypto information-aware Random/Genetic generators."""
from __future__ import annotations

import numpy as np

from ..grammar import CATALOG
from ..strategy import Predicate
from ..generators.random import RandomGenerator
from ..generators.genetic import GeneticGenerator


class CryptoPredicateMixin:
    def __init__(self, *args, information_variant="PRICE", **kwargs):
        self.information_variant = information_variant.upper()
        super().__init__(*args, **kwargs)

    def sample_predicate(self):
        families = ["Trend", "Momentum", "Volatility", "Structure"]
        predicates = []
        if self.information_variant in {"PRICE_VOLUME", "PRICE_VOLUME_FUNDING"}:
            predicates += [Predicate("crypto.volume_relative.96", op, value) for op in (">", "<") for value in (0.8, 1.0, 1.25, 1.5, 2.0)]
            predicates += [Predicate("crypto.volume_roc.16", op, value) for op in (">", "<") for value in (-0.5, -0.1, 0.1, 0.5)]
            families += []
        if self.information_variant in {"PRICE_FUNDING", "PRICE_VOLUME_FUNDING"}:
            predicates += [Predicate("crypto.funding.rate", op, value) for op in (">", "<") for value in (-0.0001, -0.00003, 0.0, 0.00003, 0.0001)]
            predicates += [Predicate("crypto.funding.change.8", op, value) for op in (">", "<") for value in (-0.0002, -0.00005, 0.00005, 0.0002)]
        if self.rng.random() < 0.45 and predicates:
            return predicates[int(self.rng.integers(len(predicates)))]
        family = families[int(self.rng.integers(len(families)))]
        return CATALOG[family][int(self.rng.integers(len(CATALOG[family])))]


class CryptoRandomGenerator(CryptoPredicateMixin, RandomGenerator):
    pass


class CryptoGeneticGenerator(CryptoPredicateMixin, GeneticGenerator):
    pass
