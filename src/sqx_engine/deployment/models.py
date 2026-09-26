from __future__ import annotations
from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import sqlite3

from ..strategy import StrategyDefinition


@dataclass(frozen=True)
class PropProfile:
    name: str = "GENERIC_PROP_V1"
    target_pct: float = .10
    daily_loss_pct: float = .05
    max_loss_pct: float = .10
    min_days: int = 4
    max_calendar_days: int | None = None
    internal_daily_limit_pct: float | None = None
    internal_total_limit_pct: float | None = None

    @classmethod
    def from_json(cls, raw: str | dict):
        x = json.loads(raw) if isinstance(raw, str) else dict(raw)
        return cls(**{k: x[k] for k in cls.__dataclass_fields__ if k in x})


@dataclass(frozen=True)
class PortfolioStrategy:
    strategy: StrategyDefinition
    weight: float


@dataclass(frozen=True)
class PortfolioDefinition:
    portfolio_id: str
    portfolio_hash: str
    strategies: tuple[PortfolioStrategy, ...]
    risk_policy: str = "PORTFOLIO_TOTAL_RISK"
    base_risk: float = .01
    max_open_risk: float = .02
    prop_profile: PropProfile = field(default_factory=PropProfile)
    status: str = "READY_FOR_PAPER"

    @property
    def strategy_ids(self):
        return tuple(x.strategy.readable_id for x in self.strategies)

    @classmethod
    def from_sqlite(cls, path: str | Path, portfolio_id: str, strategy_db: str | Path = "library/strategies.sqlite"):
        pc = sqlite3.connect(path); pc.row_factory = sqlite3.Row
        row = pc.execute("select * from portfolios where portfolio_id=?", (portfolio_id,)).fetchone()
        pc.close()
        if not row: raise KeyError(f"Portfolio not found: {portfolio_id}")
        sc = sqlite3.connect(strategy_db); sc.row_factory = sqlite3.Row
        ids = json.loads(row["strategy_ids"]); weights = json.loads(row["weights"])
        out = []
        for sid in ids:
            sr = sc.execute("select strategy_id,strategy_json from strategies where strategy_id=?", (sid,)).fetchone()
            if not sr: raise KeyError(f"Strategy not found: {sid}")
            out.append(PortfolioStrategy(replace(StrategyDefinition.from_json(sr["strategy_json"]), strategy_id=sid), float(weights[sid])))
        sc.close()
        profile = PropProfile.from_json(row["prop_profile"])
        return cls(row["portfolio_id"], row["portfolio_hash"], tuple(out), row["risk_policy"], float(row["risk_budget"]), .02, profile, row["status"])

    @classmethod
    def from_yaml(cls, path: str | Path, strategy_db: str | Path = "library/strategies.sqlite"):
        import yaml
        x = yaml.safe_load(Path(path).read_text())
        sc = sqlite3.connect(strategy_db); sc.row_factory = sqlite3.Row
        out = []
        for item in x["strategies"]:
            r = sc.execute("select strategy_json from strategies where strategy_id=?", (item["strategy_id"],)).fetchone()
            if not r: raise KeyError(item["strategy_id"])
            out.append(PortfolioStrategy(replace(StrategyDefinition.from_json(r[0]), strategy_id=item["strategy_id"]), float(item["weight"])))
        sc.close()
        risk = x.get("risk", {})
        return cls(x["portfolio_id"], x.get("portfolio_hash", ""), tuple(out), risk.get("policy", "PORTFOLIO_TOTAL_RISK"), float(risk.get("base_risk_pct", .01)), float(risk.get("max_open_risk_pct", .02)), PropProfile.from_json(x.get("prop_profile", "GENERIC_PROP_V1")), x.get("status", "READY_FOR_PAPER"))
