from __future__ import annotations

from dataclasses import replace
import numpy as np

from .random import RandomGenerator
from ..strategy import Predicate, StrategyDefinition


class GeneticGenerator(RandomGenerator):
    """Deterministic tournament/crossover/mutation generator for V1.1."""

    def __init__(self, *args, population_size=40, mutation_rate=.35, crossover_rate=.70,
                 mode="legacy", novelty_retry_limit=8, immigrant_after=2, **kwargs):
        super().__init__(*args, **kwargs)
        self.population_size = int(population_size)
        self.mutation_rate, self.crossover_rate = float(mutation_rate), float(crossover_rate)
        self.mode = str(mode)
        self.novelty_retry_limit = max(0, int(novelty_retry_limit))
        self.immigrant_after = max(1, int(immigrant_after))
        self.population = []
        self.elite = []
        self._elite_hashes = set()
        self.generation = 0
        self.telemetry = {"mutation_attempts": 0, "mutation_effective": 0,
                          "mutation_noop": 0, "crossover_attempts": 0,
                          "crossover_effective": 0, "crossover_noop": 0,
                          "novelty_retries": 0, "global_duplicate": 0}
        self.telemetry["immigrant_attempts"] = 0
        self.telemetry["immigrant_unique"] = 0

    def _mutate(self, strategy):
        fields = ["direction", "stop_atr", "target_atr", "time_exit", "logic"]
        if self.rng.random() < self.mutation_rate:
            before = strategy.canonical_hash
            field = str(self.rng.choice(fields))
            if field == "direction": strategy = replace(strategy, direction="SHORT" if strategy.direction == "LONG" else "LONG")
            elif field == "stop_atr":
                values = [1., 1.5, 2., 2.5]
                if self.mode == "scale": values = [x for x in values if x != strategy.stop_atr]
                strategy = replace(strategy, stop_atr=float(self.rng.choice(values)))
            elif field == "target_atr":
                values = [1.5, 2., 3., 4.]
                if self.mode == "scale": values = [x for x in values if x != strategy.target_atr]
                strategy = replace(strategy, target_atr=float(self.rng.choice(values)))
            elif field == "time_exit":
                values = [24, 48, 72, 96]
                if self.mode == "scale": values = [x for x in values if x != strategy.time_exit]
                strategy = replace(strategy, time_exit=int(self.rng.choice(values)))
            else: strategy = replace(strategy, logic="OR" if strategy.logic == "AND" else "AND")
            if self.mode == "scale":
                self.telemetry["mutation_attempts"] += 1
                self.telemetry["mutation_effective"] += int(strategy.canonical_hash != before)
        if self.grammar_version == 'v1.7':
            if self.rng.random() < self.mutation_rate:
                before = strategy.canonical_hash
                ps = list(strategy.predicates)
                operation = str(self.rng.choice(['replace', 'add', 'remove']))
                if operation == 'add' and len(ps) < self.max_predicates:
                    ps = list(self.complete_predicates(ps, len(ps) + 1))
                elif operation == 'remove' and len(ps) > self.min_predicates:
                    ps.pop(int(self.rng.integers(len(ps))))
                else:
                    i = int(self.rng.integers(len(ps)))
                    replacement = self.sample_predicate()
                    while replacement in ps: replacement = self.sample_predicate()
                    ps[i] = replacement
                strategy = replace(strategy, predicates=tuple(ps))
                self.telemetry['mutation_attempts'] += 1
                self.telemetry['mutation_effective'] += int(strategy.canonical_hash != before)
            return strategy
        if self.rng.random() < self.mutation_rate and strategy.predicates:
            before = strategy.canonical_hash
            i = int(self.rng.integers(0, len(strategy.predicates))); p = strategy.predicates[i]
            values = [10, 20, 25, 30, 35, 40, 50, 60, 70, 80, 100] if p.feature.startswith("ema") else ([25, 30, 35, 40, 50, 60, 65, 70, 75] if p.feature.startswith("rsi") else [15, 20, 25, 30, 35, 40])
            if self.mode == "scale": values = [x for x in values if float(x) != float(p.value)]
            ps = list(strategy.predicates); ps[i] = Predicate(p.feature, ">" if p.operator == "<" else "<", float(self.rng.choice(values)))
            strategy = replace(strategy, predicates=tuple(ps))
            if self.mode == "scale":
                self.telemetry["mutation_attempts"] += 1
                self.telemetry["mutation_effective"] += int(strategy.canonical_hash != before)
        if self.mode == "scale" and strategy.canonical_hash == getattr(self, "_last_mutation_hash", None):
            self.telemetry["mutation_noop"] += 1
        self._last_mutation_hash = strategy.canonical_hash
        return strategy

    def _crossover(self, a, b):
        if self.mode == "scale": self.telemetry["crossover_attempts"] += 1
        predicates = tuple((list(a.predicates) + list(b.predicates))[: self.max_predicates]) or a.predicates
        if self.grammar_version == 'v1.7':
            pool = list(dict.fromkeys(a.predicates + b.predicates))
            self.rng.shuffle(pool)
            size = int(self.rng.integers(self.min_predicates, min(self.max_predicates, len(pool)) + 1))
            predicates = self.complete_predicates(pool, size)
        child = StrategyDefinition(self.market, self.timeframe, a.direction if self.rng.random() < .5 else b.direction, predicates, a.logic if self.rng.random() < .5 else b.logic, 14, a.stop_atr if self.rng.random() < .5 else b.stop_atr, a.target_atr if self.rng.random() < .5 else b.target_atr, a.time_exit if self.rng.random() < .5 else b.time_exit, grammar_version=self.grammar_version)
        if self.mode == "scale":
            same = child.canonical_hash in {a.canonical_hash, b.canonical_hash}
            self.telemetry["crossover_noop"] += int(same)
            self.telemetry["crossover_effective"] += int(not same)
        return child

    def ask(self, known_hashes=None):
        if len(self.elite) < 2 or self.generated < self.population_size:
            strategy = super().ask()
        else:
            retries = self.novelty_retry_limit if self.mode == "scale" else 0
            for retry in range(retries + 1):
                a = self.elite[int(self.rng.integers(0, len(self.elite)))][0]
                b = self.elite[int(self.rng.integers(0, len(self.elite)))][0]
                strategy = self._crossover(a, b) if self.rng.random() < self.crossover_rate else a
                strategy = self._mutate(strategy)
                duplicate = strategy.canonical_hash in self._elite_hashes or (known_hashes is not None and strategy.canonical_hash in known_hashes)
                if self.mode != "scale" or not duplicate or retry == retries:
                    break
                self.telemetry["novelty_retries"] += 1
                self.telemetry["global_duplicate"] += int(known_hashes is not None and strategy.canonical_hash in known_hashes)
                if retry + 1 >= self.immigrant_after:
                    # A bounded random immigrant breaks convergence without an
                    # unbounded novelty loop. It is still checked by the
                    # coordinator's global set before evaluation.
                    self.telemetry["immigrant_attempts"] += 1
                    strategy = super().ask()
                    self.generated -= 1
                    if known_hashes is None or strategy.canonical_hash not in known_hashes:
                        self.telemetry["immigrant_unique"] += 1
                        break
            if self.mode == "legacy":
                if strategy.canonical_hash in self._elite_hashes:
                    strategy = self._mutate(super().ask())
                else:
                    self.generated += 1
            else:
                self.generated += 1
        return strategy

    def tell(self, strategy, result):
        score = float(getattr(result, "expectancy_r", -1e9)) + .1 * float(getattr(result, "sharpe", 0)) - float(getattr(result, "max_drawdown", 1))
        self.population.append((strategy, score))
        ranked = sorted(self.population, key=lambda x: (x[1], x[0].canonical_hash), reverse=True)
        self.elite = ranked[: self.population_size]
        if self.mode == "scale":
            # The legacy state retains its full history for exact compatibility.
            # Scale mode only needs the bounded breeding pool; keeping all
            # evaluated individuals made each tell increasingly more expensive.
            self.population = self.elite[:]
        self._elite_hashes = {x[0].canonical_hash for x in self.elite}
        if self.generated and self.generated % self.population_size == 0:
            self.generation += 1

    def state(self):
        return {**super().state(), "generated": self.generated, "generation": self.generation, "rng_state": self.rng.bit_generator.state,
                "mode": self.mode, "telemetry": self.telemetry,
                "population": [(s.to_json(), score) for s, score in self.population],
                "elite": [(s.to_json(), score) for s, score in self.elite]}

    def set_state(self, state):
        super().set_state(state)
        self.generation = int(state.get("generation", 0))
        self.population = [(StrategyDefinition.from_json(raw), float(score)) for raw, score in state.get("population", [])]
        self.elite = []
        for raw, score in state.get("elite", []):
            self.elite.append((StrategyDefinition.from_json(raw), float(score)))
        self._elite_hashes = {x[0].canonical_hash for x in self.elite}
        self.telemetry.update(state.get("telemetry", {}))
