"""Canonical economic specifications and frozen geometry helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class StrategyEconomicSpec:
    strategy_id: str
    canonical_hash: str
    market: str
    timeframe: str
    direction: str
    stop_model: str
    target_model: str
    time_exit_model: str
    stop_atr: float
    target_atr: float
    time_exit_bars: int
    execution_profile_id: str
    spread_status: str
    spread_model: float | None
    commission_status: str
    commission_model: str
    swap_status: str
    swap_model: str | None
    slippage_status: str
    slippage_model: float | None
    economic_spec_version: str = "UNIVERSAL_STRATEGY_ECONOMICS_V1"

    def to_dict(self):
        return asdict(self)

    def canonical_hash_value(self):
        payload = self.to_dict()
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def geometry_from_atr(entry_price: float, atr_at_signal: float, stop_atr: float,
                      target_atr: float, direction: str) -> dict:
    if not all(math.isfinite(float(x)) for x in (entry_price, atr_at_signal, stop_atr, target_atr)):
        raise ValueError("non-finite economic geometry")
    stop_distance = float(atr_at_signal) * float(stop_atr)
    target_distance = float(atr_at_signal) * float(target_atr)
    if stop_distance <= 0 or target_distance <= 0:
        raise ValueError("non-positive stop/target distance")
    sign = 1.0 if direction.upper() in {"LONG", "BUY"} else -1.0
    return {"stop_distance": stop_distance, "stop_price": float(entry_price) - sign * stop_distance,
            "target_distance": target_distance, "target_price": float(entry_price) + sign * target_distance,
            "initial_risk_price": stop_distance}


def apply_profile_cost(gross_pnl_price: float, spread: float, slippage: float) -> float:
    """Apply the frozen V1.8 round-trip price cost exactly once."""
    return float(gross_pnl_price) - float(spread) - float(slippage)


def build_prop_ready_metadata(strategy, execution_profile_id: str, *,
                              spread_model: float | None, slippage_model: float | None,
                              swap_status: str = "UNRESOLVED_GENERIC") -> dict:
    """Create the immutable metadata contract attached to future promotions.

    This is an adapter only: it reads economic fields from the frozen
    StrategyDefinition and does not mutate, regenerate, or reinterpret it.
    The caller supplies the versioned execution profile and an already
    reconstructed R ledger before setting ``PROP_READY``.
    """
    spec = StrategyEconomicSpec(
        strategy_id=str(strategy.readable_id if hasattr(strategy, "readable_id") else strategy.strategy_id),
        canonical_hash=str(strategy.canonical_hash), market=str(strategy.market),
        timeframe=str(strategy.timeframe), direction=str(strategy.direction),
        stop_model="ATR_SIGNAL_BAR", target_model="ATR_SIGNAL_BAR",
        time_exit_model="BARS", stop_atr=float(strategy.stop_atr),
        target_atr=float(strategy.target_atr), time_exit_bars=int(strategy.time_exit),
        execution_profile_id=str(execution_profile_id),
        spread_status="PROFILE_MODEL" if spread_model is not None else "UNRESOLVED",
        spread_model=spread_model, commission_status="PROFILE_MODEL",
        commission_model="PROFILE_FRICTION_ONCE_PER_TRADE",
        swap_status=str(swap_status), swap_model=None,
        slippage_status="PROFILE_MODEL" if slippage_model is not None else "UNRESOLVED",
        slippage_model=slippage_model,
    )
    return {"prop_ready": True, "economic_spec": spec.to_dict(),
            "economic_spec_hash": spec.canonical_hash_value(),
            "requires_r_ledger": True, "requires_execution_profile": True}
