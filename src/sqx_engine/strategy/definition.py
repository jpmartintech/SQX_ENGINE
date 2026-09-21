from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json

@dataclass(frozen=True)
class Predicate:
    feature: str
    operator: str
    value: float
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class StrategyDefinition:
    market: str; timeframe: str; direction: str; predicates: tuple[Predicate,...]
    logic: str="AND"; atr_period: int=14; stop_atr: float=1.5; target_atr: float=2.0; time_exit: int=48; strategy_id: str=""
    def payload(self): return {"market":self.market,"timeframe":self.timeframe,"direction":self.direction,"predicates":[p.to_dict() for p in self.predicates],"logic":self.logic,"atr_period":self.atr_period,"stop_atr":self.stop_atr,"target_atr":self.target_atr,"time_exit":self.time_exit}
    @property
    def canonical_json(self): return json.dumps(self.payload(),sort_keys=True,separators=(",",":"))
    @property
    def canonical_hash(self): return hashlib.sha256(self.canonical_json.encode()).hexdigest()
    @property
    def readable_id(self): return self.strategy_id or f"SQX-{self.market}-{self.timeframe}-{self.canonical_hash[:12]}"
    def to_json(self): return self.canonical_json

    @classmethod
    def from_json(cls, raw):
        p = json.loads(raw)
        return cls(p["market"], p["timeframe"], p["direction"], tuple(Predicate(x["feature"], x["operator"], x["value"]) for x in p["predicates"]), p.get("logic", "AND"), p.get("atr_period", 14), p.get("stop_atr", 1.5), p.get("target_atr", 2.0), p.get("time_exit", 48))
