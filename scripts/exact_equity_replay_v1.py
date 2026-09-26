"""Build the exact-equity replay inventory and MT5 calibration fixture."""
from __future__ import annotations

import hashlib
import json
import re
import resource
import time
from pathlib import Path

import pandas as pd

from sqx_engine.portfolio_factory.exact_equity import BarEquityReplay, inventory_dataset, load_ohlc
from sqx_engine.portfolio_factory.ftmo_v2 import Ftmo2StepProfile, Ftmo2StepSimulator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/exact_equity_replay_v1"
OOS = ROOT / "runs/reports/deployment_engine_v1/full_mt5_oos"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory():
    paths = []
    for market in ("EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "XAUUSD"):
        paths.append((market, "M15", ROOT / f"data/cloud/{market}_M15.csv", "native"))
        h1 = next(ROOT.glob(f"data/derived/{market}_H1_*.csv"), None)
        h4 = next(ROOT.glob(f"data/derived/{market}_H4_*.csv"), None)
        if h1: paths.append((market, "H1", h1, "derived/native-reference"))
        if h4: paths.append((market, "H4", h4, "derived"))
    rows = []
    for market, tf, path, kind in paths:
        item = inventory_dataset(path, market, tf, kind)
        item["sha256"] = sha256(path)
        rows.append(item)
    return rows


def mt5_events():
    d = pd.read_csv(OOS / "full_mt5_oos_trades.csv")
    d["entry_time"] = pd.to_datetime(d.entry_time, utc=True)
    d["exit_time"] = pd.to_datetime(d.exit_time, utc=True)
    d["direction"] = d.direction.map({"BUY": "LONG", "SELL": "SHORT"}).fillna(d.direction)
    d["market"] = d.symbol
    d["timeframe"] = d.strategy_id.str.extract(r"SQX-[^-]+-([^-]+)-", expand=False).fillna("H1")
    # Normalized capital is 1.0, so one EURUSD lot's price-unit contract
    # value is represented as 1.0 per 100K reference account, not 100,000.
    d["contract_value"] = d.volume
    d["net_return"] = d.gross_pnl / 100000.0
    d["commission_entry"] = d.commission_entry / 100000.0
    d["commission_exit"] = d.commission_exit / 100000.0
    d["swap"] = d.swap / 100000.0
    d["allocated_risk_fraction"] = (abs(d.entry_price - d.stop_price) * d.contract_value)
    return d


def main():
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    data = inventory()
    (OUT / "data_inventory.json").write_text(json.dumps({"datasets": data, "data_policy": "M15 for H1/H4 MTM; M15 for M15 strategies", "external_downloads": False}, indent=2) + "\n")
    events = mt5_events()
    risk = pd.read_csv(ROOT / "runs/reports/portfolio_factory_v1/risk_reconstruction/trade_reconstruction.csv")
    (OUT / "position_ledger_summary.json").write_text(json.dumps({
        "library_replay_rows": 1230889, "library_replay_strategy_count": 12289,
        "positions_with_explicit_stop_geometry": int(len(risk)), "strategies_with_explicit_stop_geometry": int(risk.strategy_id.nunique()),
        "mt5_reference_positions": int(len(events)), "ledger_fields": list(events.columns),
        "arbitrary_8438_coverage": "PARTIAL: general replay has entries/exits but no universal stop geometry"
    }, indent=2) + "\n")
    costs = json.loads((OOS / "full_mt5_oos_costs.json").read_text())
    (OUT / "cost_inventory.json").write_text(json.dumps({"mt5_reference": costs, "spread": "COST_UNRESOLVED_FROM_LEDGER", "commission": "COST_EXACT", "swap": "COST_EXACT_FOR_MT5_REFERENCE", "generic_library_swap": "COST_UNRESOLVED"}, indent=2) + "\n")

    bars = load_ohlc(ROOT / "data/cloud/EURUSD_M15.csv")
    replay = BarEquityReplay(Ftmo2StepProfile(), initial_equity=1.0, path_policy="BAR_PATH_CONSERVATIVE")
    result = replay.replay(events, bars, market="EURUSD")
    telemetry = result["telemetry"]
    telemetry.to_csv(OUT / "daily_equity_reference.csv", index=False)
    summary = json.loads((OOS / "full_mt5_oos_summary.json").read_text())
    mt5_return = summary["mt5_summary_headline"]["net_profit"] / 100000.0
    replay_return = float(telemetry.balance.iloc[-1] - 1.0) if len(telemetry) else 0.0
    comparison = {"portfolio": "SQX-PROP-02760ECAC8BA", "period": "2024-01-01/2026-04-14", "python_replay_trades": int(len(events)), "mt5_trades": 1481, "python_return": replay_return, "mt5_return": mt5_return, "return_abs_diff": replay_return - mt5_return, "python_balance_dd": float(result["max_equity_drawdown"]), "mt5_balance_dd": summary["mt5_summary_headline"]["max_balance_dd"] / 100000.0, "python_equity_dd": float(result["max_equity_drawdown"]), "mt5_equity_dd": summary["mt5_summary_headline"]["max_equity_dd"] / 100000.0, "intrabar_ambiguous": result["intrabar_ambiguous"], "status": "CALIBRATION_ONLY"}
    (OUT / "mt5_reference_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")

    proxy_rows = []
    for risk_fraction in (.005, .01, .02):
        p = events[["entry_time", "exit_time", "net_return"]].copy()
        proxy = Ftmo2StepSimulator().run(p, target=.10, risk_fraction=risk_fraction)
        proxy_rows.append({"risk_fraction": risk_fraction, "proxy_status": proxy["status"], "proxy_return": proxy.get("return"), "bar_status": result["status"], "bar_return": replay_return, "classification": "CALIBRATION_REFERENCE"})
    pd.DataFrame(proxy_rows).to_csv(OUT / "proxy_vs_exact.csv", index=False)
    (OUT / "intrabar_ambiguity.json").write_text(json.dumps({"ambiguous_position_bar_hits": result["intrabar_ambiguous"], "policy": "BAR_PATH_CONSERVATIVE; adverse valid OHLC scenario", "tick_exact": False}, indent=2) + "\n")

    benchmarks = []
    for n in (20, 50, 100):
        sample = events.head(n).copy(); t0 = time.perf_counter(); r = replay.replay(sample, bars, market="EURUSD"); elapsed = time.perf_counter() - t0
        benchmarks.append({"portfolio_size": n, "positions": n, "bars": int(len(r["telemetry"])), "seconds": elapsed, "bars_per_second": len(r["telemetry"]) / max(elapsed, 1e-9), "rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024})
    benchmarks.append({"portfolio_size": "FAST_PROXY", "seconds": None, "note": "Existing closed-trade proxy; not a comparable bar-loop benchmark"})
    (OUT / "performance_benchmark.json").write_text(json.dumps({"benchmarks": benchmarks, "disk_bytes": sum(p.stat().st_size for p in OUT.glob("*"))}, indent=2) + "\n")
    report = f"""# SQX EXACT EQUITY REPLAY V1 — REPORT

Baseline: `79e1f68979be745badbd88b5e3c1febe2c7f2869`

The replay layer is implemented at bar resolution. M15 is used to mark H1/H4 positions and M15 positions. It supports normalized floating P/L, realized balance, daily equity floors in Europe/Paris, static maximum loss, open-risk aggregation, costs, simultaneous positions, and conservative OHLC path probes.

The MT5 reference portfolio contains {len(events)} positions and was replayed against EURUSD M15. Reconstructed normalized return was {replay_return:.8f} versus MT5 {mt5_return:.8f}; this is calibration evidence, not a claim of exact broker replication. The replay is not tick-exact and its bar adverse path is conservative. Ambiguous stop/target hits: {result['intrabar_ambiguous']}.

Critical coverage limitation: the general 12,289-strategy replay has entry/exit outcomes but no universal initial-stop geometry. Explicit stop geometry currently covers {len(risk)} reconstructed positions across {risk.strategy_id.nunique()} strategies. Therefore arbitrary 8,438-strategy exact FTMO replay is not yet certifiable.

Costs: commission and swap are exact where present in the MT5 ledger; spread is unresolved from the normalized trade ledger; generic-library swap remains unresolved. No external data was downloaded.

The next step before FTMO discovery is to produce/attach universal stop geometry and cost metadata for the certified universe, then rerun this replay with exact strategy position ledgers.
"""
    (OUT / "exact_equity_replay_report.md").write_text(report)
    print(json.dumps({"positions": len(events), "replay_return": replay_return, "mt5_return": mt5_return, "ambiguity": result["intrabar_ambiguous"], "runtime": time.perf_counter() - started}, indent=2))


if __name__ == "__main__":
    main()
