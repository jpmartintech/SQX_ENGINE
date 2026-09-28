"""Venue-specific Hyperliquid perpetual economics.

This module deliberately does not reuse Forex pip or swap semantics.  It is
an immutable, normalized contract used before leverage is applied.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class CryptoExecutionCost:
    """One-way execution assumptions, expressed as decimal fractions."""

    maker_fee_rate: float = 0.00015
    taker_fee_rate: float = 0.00045
    slippage_rate: float = 0.00010
    fee_side: str = "TAKER"
    version: str = "HYPERLIQUID_COST_V1"

    def __post_init__(self):
        if self.fee_side not in {"MAKER", "TAKER"}:
            raise ValueError("fee_side must be MAKER or TAKER")
        for value in (self.maker_fee_rate, self.taker_fee_rate, self.slippage_rate):
            if not math.isfinite(value) or value < 0:
                raise ValueError("execution costs must be finite and non-negative")

    @property
    def fee_rate(self) -> float:
        return self.maker_fee_rate if self.fee_side == "MAKER" else self.taker_fee_rate


@dataclass(frozen=True)
class CryptoEconomicSpecV1:
    symbol: str
    quote_asset: str = "USDC"
    perpetual_type: str = "LINEAR_PERPETUAL"
    sz_decimals: int = 5
    min_quantity: float = 0.0
    tick_size: float = 0.0
    maker_fee_rate: float = 0.00015
    taker_fee_rate: float = 0.00045
    slippage_rate: float = 0.00010
    funding_interval_hours: int = 1
    margin_mode: str = "CROSS_OR_ISOLATED"
    leverage: float = 1.0
    maintenance_margin_fraction: float | None = None
    mark_source: str = "HYPERLIQUID_MARK"
    funding_source: str = "HYPERLIQUID_REALIZED_FUNDING"
    version: str = "CRYPTO_ECONOMIC_SPEC_V1"

    def __post_init__(self):
        if not self.symbol or self.perpetual_type != "LINEAR_PERPETUAL":
            raise ValueError("unsupported crypto contract")
        if self.leverage < 1 or not math.isfinite(self.leverage):
            raise ValueError("leverage must be finite and >= 1")
        if self.funding_interval_hours <= 0:
            raise ValueError("funding interval must be positive")
        if self.maintenance_margin_fraction is not None and not 0 < self.maintenance_margin_fraction < 1:
            raise ValueError("invalid maintenance margin fraction")

    def to_dict(self) -> dict:
        return asdict(self)

    def canonical_hash(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


def funding_pnl(position_size: float, oracle_price: float, funding_rate: float, direction: str) -> float:
    """Return the trader's funding PnL at a realized settlement.

    Positive funding is paid by longs and received by shorts.  The rate is
    applied to notional at the authoritative oracle price.
    """
    if direction.upper() not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
    if not all(math.isfinite(float(x)) for x in (position_size, oracle_price, funding_rate)):
        raise ValueError("funding inputs must be finite")
    payment = abs(position_size) * oracle_price * funding_rate
    return -payment if direction.upper() == "LONG" else payment


def liquidation_price(entry_price: float, direction: str, leverage: float,
                      maintenance_margin_fraction: float) -> float:
    """Conservative isolated linear-perp liquidation approximation.

    Exact venue margin tiers must replace this approximation before live
    deployment.  It is intentionally explicit rather than hidden in sizing.
    """
    if entry_price <= 0 or leverage < 1 or not 0 < maintenance_margin_fraction < 1:
        raise ValueError("invalid liquidation inputs")
    direction = direction.upper()
    if direction == "LONG":
        return entry_price * (1 - 1 / leverage + maintenance_margin_fraction)
    if direction == "SHORT":
        return entry_price * (1 + 1 / leverage - maintenance_margin_fraction)
    raise ValueError("direction must be LONG or SHORT")
