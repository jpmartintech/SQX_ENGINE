from __future__ import annotations
from dataclasses import dataclass, asdict, field
import hashlib, json

@dataclass(frozen=True)
class Predicate:
    feature: str
    operator: str
    value: float
    def __post_init__(self):
        if self.operator not in {">", "<", "=="}: raise ValueError("Unsupported predicate operator")
        if self.feature.startswith('trend.ema_pair.'):
            parts = self.feature.split('.')
            fast, slow = map(int, parts[2:])
            if fast == slow or self.value != 0 or self.operator == '==': raise ValueError('EMA pairs require distinct periods and zero comparison')
            if fast > slow:
                object.__setattr__(self, 'feature', f'trend.ema_pair.{slow}.{fast}')
                object.__setattr__(self, 'operator', '<' if self.operator == '>' else '>')

    @property
    def semantic(self):
        if self.feature.startswith('trend.ema_slope.'):
            return 'EMA_SLOPE_UP' if self.operator == '>' else 'EMA_SLOPE_DOWN'
        return self.feature

    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class StrategyDefinition:
    market: str; timeframe: str; direction: str; predicates: tuple[Predicate,...]
    logic: str="AND"; atr_period: int=14; stop_atr: float=1.5; target_atr: float=2.0; time_exit: int=48; strategy_id: str=""
    grammar_version: str = "legacy"
    _canonical_json_cache: str = field(default="", init=False, repr=False, compare=False)
    _canonical_hash_cache: str = field(default="", init=False, repr=False, compare=False)
    def __post_init__(self):
        if self.grammar_version not in {'legacy', 'v1.7'}: raise ValueError('Unknown grammar version')
        if self.grammar_version == 'v1.7':
            normalized = (Predicate(p.feature, p.operator, float(p.value)) for p in self.predicates)
            predicates = tuple(sorted(set(normalized), key=lambda p: (p.feature, p.operator, float(p.value))))
            if not 1 <= len(predicates) <= 4: raise ValueError('V1.7 requires 1–4 distinct predicates')
            if self.logic not in {'AND', 'OR'}: raise ValueError('Invalid strategy logic')
            object.__setattr__(self, 'predicates', predicates)
            if len(predicates) == 1: object.__setattr__(self, 'logic', 'AND')

    def payload(self):
        payload = {"market":self.market,"timeframe":self.timeframe,"direction":self.direction,"predicates":[p.to_dict() for p in self.predicates],"logic":self.logic,"atr_period":self.atr_period,"stop_atr":self.stop_atr,"target_atr":self.target_atr,"time_exit":self.time_exit}
        if self.grammar_version != 'legacy': payload['grammar_version'] = self.grammar_version
        return payload
    @property
    def canonical_json(self):
        value = self._canonical_json_cache
        if not value:
            value = json.dumps(self.payload(), sort_keys=True, separators=(",", ":"))
            object.__setattr__(self, "_canonical_json_cache", value)
        return value
    @property
    def canonical_hash(self):
        value = self._canonical_hash_cache
        if not value:
            value = hashlib.sha256(self.canonical_json.encode()).hexdigest()
            object.__setattr__(self, "_canonical_hash_cache", value)
        return value
    @property
    def readable_id(self): return self.strategy_id or f"SQX-{self.market}-{self.timeframe}-{self.canonical_hash[:12]}"
    def to_json(self): return self.canonical_json

    @classmethod
    def from_json(cls, raw):
        p = json.loads(raw)
        return cls(p["market"], p["timeframe"], p["direction"], tuple(Predicate(x["feature"], x["operator"], x["value"]) for x in p["predicates"]), p.get("logic", "AND"), p.get("atr_period", 14), p.get("stop_atr", 1.5), p.get("target_atr", 2.0), p.get("time_exit", 48), grammar_version=p.get("grammar_version", "legacy"))
