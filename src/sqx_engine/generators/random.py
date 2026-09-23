from __future__ import annotations
import numpy as np
from .base import StrategyGenerator
from ..strategy import Predicate, StrategyDefinition

class RandomGenerator(StrategyGenerator):
    def __init__(self, market, timeframe, seed=101, max_predicates=2):
        self.market=market; self.timeframe=timeframe; self.rng=np.random.default_rng(seed); self.max_predicates=max_predicates; self.generated=0
        self.features=("ema_10","ema_20","ema_50","ema_100","rsi_14","adx_14","close")
    def ask(self, known_hashes=None):
        n=int(self.rng.integers(1,self.max_predicates+1)); ps=[]
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
        return {"generated": self.generated, "rng_state": self.rng.bit_generator.state}

    def set_state(self, state):
        self.generated = int(state.get("generated", 0))
        if state.get("rng_state"):
            self.rng.bit_generator.state = state["rng_state"]
