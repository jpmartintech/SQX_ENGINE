from __future__ import annotations
import numpy as np
from .base import StrategyGenerator
from ..strategy import Predicate, StrategyDefinition

class RandomGenerator(StrategyGenerator):
    def __init__(self, market, timeframe, seed=101, max_predicates=2, min_predicates=1, grammar_version="legacy"):
        self.market=market; self.timeframe=timeframe; self.rng=np.random.default_rng(seed); self.max_predicates=max_predicates; self.generated=0
        self.min_predicates = int(min_predicates)
        self.grammar_version = grammar_version
        if grammar_version not in {'legacy', 'v1.7'}: raise ValueError('Unknown grammar version')
        if not 1 <= self.min_predicates <= self.max_predicates <= 4: raise ValueError('Expected 1 <= min_predicates <= max_predicates <= 4')
        self.features=("ema_10","ema_20","ema_50","ema_100","rsi_14","adx_14","close")
    def sample_predicate(self):
        from ..grammar import FAMILIES, CATALOG
        family = FAMILIES[int(self.rng.integers(len(FAMILIES)))]
        return CATALOG[family][int(self.rng.integers(len(CATALOG[family])))]

    def complete_predicates(self, predicates, size):
        ps = list(dict.fromkeys(predicates))[:size]
        while len(ps) < size:
            p = self.sample_predicate()
            if p not in ps: ps.append(p)
        return tuple(ps)

    def ask(self, known_hashes=None):
        if self.grammar_version == 'v1.7':
            n = int(self.rng.integers(self.min_predicates, self.max_predicates + 1))
            predicates = self.complete_predicates((), n)
            self.generated += 1
            return StrategyDefinition(self.market, self.timeframe, str(self.rng.choice(['LONG', 'SHORT'])), predicates,
                                      str(self.rng.choice(['AND', 'OR'])) if n > 1 else 'AND', 14,
                                      float(self.rng.choice([1., 1.5, 2., 2.5])),
                                      float(self.rng.choice([1.5, 2., 3., 4.])), int(self.rng.choice([24, 48, 72, 96])),
                                      grammar_version='v1.7')
        n=int(self.rng.integers(self.min_predicates,self.max_predicates+1)); ps=[]
        for _ in range(n):
            f=str(self.rng.choice(self.features)); op=str(self.rng.choice([">","<"]))
            if f.startswith("ema_"): value=float(self.rng.choice([10,20,30,40,50,60,70,80,100]))
            elif f.startswith("rsi"): value=float(self.rng.choice([25,30,35,40,50,60,65,70,75]))
            elif f.startswith("adx"): value=float(self.rng.choice([15,20,25,30,35,40]))
            else: value=float(self.rng.choice([0.998,0.999,1.0,1.001,1.002]))
            ps.append(Predicate(f,op,value))
        if len({p.to_dict().__repr__() for p in ps}) != len(ps): return self.ask(known_hashes)
        self.generated+=1
        return StrategyDefinition(self.market,self.timeframe,str(self.rng.choice(["LONG","SHORT"])),tuple(ps),str(self.rng.choice(["AND","OR"] if n==2 else ["AND"])),14,float(self.rng.choice([1.0,1.5,2.0])),float(self.rng.choice([1.5,2.0,3.0])),int(self.rng.choice([24,48,72])))

    def state(self):
        return {"generated": self.generated, "rng_state": self.rng.bit_generator.state, "grammar_version": self.grammar_version, "min_predicates": self.min_predicates, "max_predicates": self.max_predicates}

    def set_state(self, state):
        if state.get('grammar_version', 'legacy') != self.grammar_version:
            raise ValueError('Checkpoint grammar mismatch')
        if self.grammar_version == 'v1.7' and (state.get('min_predicates') != self.min_predicates or state.get('max_predicates') != self.max_predicates):
            raise ValueError('Checkpoint composition mismatch')
        self.generated = int(state.get("generated", 0))
        if state.get("rng_state"):
            self.rng.bit_generator.state = state["rng_state"]
