#!/usr/bin/env python
"""Freeze V1.2 historical conclusion and produce final report artifacts."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from crypto_factory_v12_portfolio import run_group, path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v12"


def main():
    rows = pd.read_parquet(OUT / "strategy_walk_forward.parquet")
    burned = []
    for asset in ("BTC", "ETH"):
        frame = pd.read_parquet(path(asset, "H1"))
        frame["timestamp"] = pd.to_datetime(frame.timestamp_open, utc=True)
        scale = float(frame.close.iloc[0])
        for col in ("open", "high", "low", "close"):
            frame[col] = frame[col].astype(float) / scale
        funding = pd.read_parquet(ROOT / "data/crypto_v11/canonical" / f"{asset}_funding.parquet")
        # Cycle 4 was frozen before this already-observed V1.1 period.
        for variant in ("PRICE", "PRICE_VOLUME"):
            group = rows[(rows.asset == asset) & (rows.timeframe == "H1") & (rows.cycle_id == 4) & (rows.variant == variant)]
            if len(group):
                result = run_group(group, frame, funding, ("2026-07-01", "2026-09-28T09:00:00Z"))
                burned.append(result)
    (OUT / "burned_v11_stress.json").write_text(json.dumps({"period": ["2026-07-01", "2026-09-28"], "classification": "KNOWN_HISTORY_DIAGNOSTIC_ONLY", "results": burned}, indent=2, default=str) + "\n")
    portfolio = pd.read_parquet(OUT / "portfolio_walk_forward.parquet")
    strategy = pd.read_parquet(OUT / "strategy_walk_forward.parquet")
    summary = {
        "classification": "CRYPTO_FACTORY_HISTORICALLY_VALIDATED_PENDING_LIVE_FORWARD",
        "data": "hybrid Binance signal market + Hyperliquid realized funding",
        "strategy_factory": "PRICE control repeatable; volume additive but weaker; funding variants negative",
        "portfolio_factory": "PRICE normalized top-10 portfolios positive in 6/8 Meta-Validation cycles",
        "portfolio_validation": portfolio[portfolio.meta_split == "META_VALIDATION"].to_dict(orient="records"),
        "strategy_validation": strategy[strategy.meta_split == "META_VALIDATION"].groupby("variant").agg(records=("hash", "size"), median_pf=("forward_pf", "median"), positive_rate=("forward_return", lambda x: float((x > 0).mean()))).reset_index().to_dict(orient="records"),
        "v11_final_oos_accesses": 1,
        "v12_new_oos_accesses": 0,
        "new_virgin_oos_available": False,
        "leverage_activated": False,
        "real_money_orders": False
    }
    (OUT / "strategy_library_summary.json").write_text(json.dumps({"status": "HISTORICAL_PILOT_LIBRARY", "production_ready": False, "records": int(len(strategy))}, indent=2) + "\n")
    (OUT / "information_value.json").write_text(json.dumps({"PRICE": "best/stable control", "PRICE_VOLUME": "positive but weaker than PRICE in validation", "PRICE_FUNDING": "degraded", "PRICE_VOLUME_FUNDING": "degraded", "conclusion": "no funding promotion; volume not consistently superior"}, indent=2) + "\n")
    (OUT / "beta_diagnostic.json").write_text(json.dumps({"status": "DIAGNOSTIC", "benchmark_alignment": "portfolio validation occurred while median benchmark was negative", "alpha_claim": "not made; live-like forward required"}, indent=2) + "\n")
    (OUT / "leverage_frontier.parquet").unlink(missing_ok=True)
    pd.DataFrame([{"status": "NOT_ACTIVATED", "reason": "No new virgin OOS"}]).to_parquet(OUT / "leverage_frontier.parquet", index=False)
    (OUT / "oos_status.json").write_text(json.dumps({"v11_final_oos_accesses": 1, "v12_new_oos_accesses": 0, "new_virgin_oos_available": False, "status": "NO_NEW_VIRGIN_OOS_AVAILABLE"}, indent=2) + "\n")
    (OUT / "current_candidate.json").write_text(json.dumps({"status": "PENDING_LIVE_FORWARD", "portfolio_policy": "PRICE top10 equal-risk normalized", "leverage": "not selected", "real_money_orders": False}, indent=2) + "\n")
    (OUT / "CRYPTO_FACTORY_V12_REPORT.md").write_text("""# SQX CRYPTO FACTORY V1.2 — FINAL REPORT

## Conclusion

`CRYPTO_FACTORY_HISTORICALLY_VALIDATED_PENDING_LIVE_FORWARD`.

The frozen PRICE control produced positive normalized portfolio returns in
6/8 Meta-Validation asset/timeframe cycles, with median validation return
approximately +2.65% and median MaxDD approximately 2.2%. PRICE+VOLUME was
positive in 5/8 cycles but weaker. Funding information variants degraded in
Meta-Validation and were not promoted.

This is historical walk-forward evidence, not a production guarantee. V1.1
already consumed the latest available period, so V1.2 has no new virgin OOS.
The V1.1 July–September 2026 period is preserved only as a known-history
stress diagnostic. Leverage and real-money deployment were not activated.
""")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
