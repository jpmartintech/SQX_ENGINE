from __future__ import annotations

import numpy as np

from .random import RandomGenerator


class GeneticGenerator(RandomGenerator):
    """Small V1 genetic-compatible generator façade.

    The evaluator remains completely outside the generator.  This gives the
    factory a stable ask/tell seam while the richer crossover/mutation engine
    is developed in a later milestone.
    """

    def __init__(self, *args, population_size=20, **kwargs):
        super().__init__(*args, **kwargs)
        self.population_size = population_size
        self.population = []

    def ask(self):
        strategy = super().ask()
        self.population.append(strategy)
        return strategy

    def tell(self, strategy, result):
        if result is not None and getattr(result, "expectancy_r", -np.inf) > 0:
            self.population.append(strategy)
        if len(self.population) > self.population_size * 2:
            self.population = self.population[-self.population_size :]
