from __future__ import annotations

from dataclasses import replace
import numpy as np

from .random import RandomGenerator
from ..strategy import Predicate, StrategyDefinition


class GeneticGenerator(RandomGenerator):
    """Deterministic tournament/crossover/mutation generator for V1.1."""

    def __init__(self, *args, population_size=40, mutation_rate=.35, crossover_rate=.70, **kwargs):
        super().__init__(*args, **kwargs)
        self.population_size = int(population_size)
        self.mutation_rate, self.crossover_rate = float(mutation_rate), float(crossover_rate)
        self.population = []
        self.elite = []
        self.generation = 0

    def _mutate(self, strategy):
        fields = ["direction", "stop_atr", "target_atr", "time_exit", "logic"]
        if self.rng.random() < self.mutation_rate:
            field = str(self.rng.choice(fields))
            if field == "direction": strategy = replace(strategy, direction="SHORT" if strategy.direction == "LONG" else "LONG")
            elif field == "stop_atr": strategy = replace(strategy, stop_atr=float(self.rng.choice([1., 1.5, 2., 2.5])))
            elif field == "target_atr": strategy = replace(strategy, target_atr=float(self.rng.choice([1.5, 2., 3., 4.])))
            elif field == "time_exit": strategy = replace(strategy, time_exit=int(self.rng.choice([24, 48, 72, 96])))
            else: strategy = replace(strategy, logic="OR" if strategy.logic == "AND" else "AND")
        if self.rng.random() < self.mutation_rate and strategy.predicates:
            i = int(self.rng.integers(0, len(strategy.predicates))); p = strategy.predicates[i]
            values = [10, 20, 25, 30, 35, 40, 50, 60, 70, 80, 100] if p.feature.startswith("ema") else ([25, 30, 35, 40, 50, 60, 65, 70, 75] if p.feature.startswith("rsi") else [15, 20, 25, 30, 35, 40])
            ps = list(strategy.predicates); ps[i] = Predicate(p.feature, ">" if p.operator == "<" else "<", float(self.rng.choice(values)))
            strategy = replace(strategy, predicates=tuple(ps))
        return strategy

    def _crossover(self, a, b):
        predicates = tuple((list(a.predicates) + list(b.predicates))[: self.max_predicates]) or a.predicates
        return StrategyDefinition(self.market, self.timeframe, a.direction if self.rng.random() < .5 else b.direction, predicates, a.logic if self.rng.random() < .5 else b.logic, 14, a.stop_atr if self.rng.random() < .5 else b.stop_atr, a.target_atr if self.rng.random() < .5 else b.target_atr, a.time_exit if self.rng.random() < .5 else b.time_exit)

    def ask(self):
        if len(self.elite) < 2 or self.generated < self.population_size:
            strategy = super().ask()
        else:
            a = self.elite[int(self.rng.integers(0, len(self.elite)))][0]
            b = self.elite[int(self.rng.integers(0, len(self.elite)))][0]
            strategy = self._crossover(a, b) if self.rng.random() < self.crossover_rate else a
            strategy = self._mutate(strategy)
            # A mutation may be a no-op; one more mutation keeps evolution active.
            if strategy.canonical_hash in {x[0].canonical_hash for x in self.elite}:
                strategy = self._mutate(super().ask())
            else:
                self.generated += 1
        return strategy

    def tell(self, strategy, result):
        score = float(getattr(result, "expectancy_r", -1e9)) + .1 * float(getattr(result, "sharpe", 0)) - float(getattr(result, "max_drawdown", 1))
        self.population.append((strategy, score))
        self.elite = sorted(self.population, key=lambda x: (x[1], x[0].canonical_hash), reverse=True)[: self.population_size]
        if self.generated and self.generated % self.population_size == 0:
            self.generation += 1

    def state(self):
        return {"generated": self.generated, "generation": self.generation, "rng_state": self.rng.bit_generator.state,
                "population": [(s.to_json(), score) for s, score in self.population],
                "elite": [(s.to_json(), score) for s, score in self.elite]}

    def set_state(self, state):
        super().set_state(state)
        self.generation = int(state.get("generation", 0))
        self.population = [(StrategyDefinition.from_json(raw), float(score)) for raw, score in state.get("population", [])]
        self.elite = []
        for raw, score in state.get("elite", []):
            self.elite.append((StrategyDefinition.from_json(raw), float(score)))
