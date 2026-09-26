"""Build the evidence-bounded portfolio equivalence audit for January 2024.

This intentionally does not fabricate the missing MT5 deal ledger. The user
supplied only aggregate tester statistics and a partial list of observed
strategy IDs, so those facts are persisted as an aggregate observation and
all trade-level MT5 fields remain UNRESOLVED.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.backtest import FastEvaluator
from sqx_engine.deployment import PortfolioDefinition
from sqx_engine.features import prepare_features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2"
DATA = ROOT / "data/derived/EURUSD_H1_11d571e8bb3d_143197.csv"
PORTFOLIO_ID = "SQX-PROP-02760ECAC8BA"
OBSERVED_IDS = [
    "SQX-EURUSD-H1-63696db839ee", "SQX-EURUSD-H1-a18d86c3075c",
    "SQX-EURUSD-H1-108300962057", "SQX-EURUSD-H1-73f2fc6ba7b5",
    "SQX-EURUSD-H1-4c5f2833ce74", "SQX-EURUSD-H1-0cc329175f76",
    "SQX-EURUSD-H1-1320ad51f2e8", "SQX-EURUSD-H1-6d1cb5fa1910",
    "SQX-EURUSD-H1-21e4d7fab033", "SQX-EURUSD-H1-a27691004dcc",
    "SQX-EURUSD-H1-ac5da82211be", "SQX-EURUSD-H1-6edd59636707",
    "SQX-EURUSD-H1-68567f217ec0", "SQX-EURUSD-H1-bdc6d699e26f",
]
MT5_SUMMARY = {
    "trades": 66, "deals": 132, "long_trades": 48, "short_trades": 18,
    "winning_trades": 13, "losing_trades": 53, "net_profit": -856.43,
    "gross_profit": 515.82, "gross_loss": -1372.25,
    "max_balance_dd": 954.20, "max_balance_dd_pct": 0.95,
    "max_equity_dd": 964.72, "max_equity_dd_pct": 0.96,
    "profit_factor": 0.38,
}


def write_csv(name, rows, fields=None):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def build_python():
    portfolio = PortfolioDefinition.from_sqlite(
        ROOT / "data/prop_portfolio_library.sqlite", PORTFOLIO_ID,
        ROOT / "library/strategies.sqlite",
    )
    df = pd.read_csv(DATA, parse_dates=["timestamp"])
    features = prepare_features(df, grammar_version="v1.7")
    start = int(df.index[df.timestamp >= pd.Timestamp("2024-01-01", tz="UTC")][0])
    end = int(df.index[df.timestamp >= pd.Timestamp("2024-02-01", tz="UTC")][0])
    atr = np.asarray(features["atr_14"], dtype=float)
    rows, signals, counts = [], [], {}

    for member in portfolio.strategies:
        strategy = member.strategy
        evaluator = FastEvaluator(df, features, initial_capital=100000,
                                  spread=0, slippage=0, engine="python")
        result = evaluator.evaluate(strategy, start=start, end=end, rich=True)
        counts[strategy.readable_id] = len(result.trades)
        signal_mask = evaluator._signal(strategy)
        for i in np.flatnonzero(signal_mask[start:end]):
            si = start + int(i)
            if si + 1 < end:
                signals.append({
                    "strategy_id": strategy.readable_id,
                    "direction": strategy.direction,
                    "signal_time": df.timestamp.iloc[si].isoformat(),
                    "entry_time": df.timestamp.iloc[si + 1].isoformat(),
                    "entry_bar": si + 1,
                    "allocated_risk_fraction": member.weight * portfolio.base_risk,
                })
        for number, trade in enumerate(result.trades, 1):
            ei = int(df.index[df.timestamp == trade["entry_time"]][0])
            si = ei - 1
            xi = int(df.index[df.timestamp == trade["exit_time"]][0])
            distance = float(atr[si] * strategy.stop_atr)
            entry = float(df.open.iloc[ei])
            stop = entry - distance if strategy.direction == "LONG" else entry + distance
            target_distance = float(atr[si] * strategy.target_atr)
            target = entry + target_distance if strategy.direction == "LONG" else entry - target_distance
            exit_price = {
                "STOP": stop, "TARGET": target,
                "TIME": float(df.close.iloc[xi]), "END": float(df.close.iloc[xi]),
            }[trade["reason"]]
            rows.append({
                "trade_number": len(rows) + 1,
                "strategy_id": strategy.readable_id,
                "direction": trade["direction"],
                "signal_time": df.timestamp.iloc[si].isoformat(),
                "signal_bar": si,
                "entry_bar": ei,
                "entry_time": pd.Timestamp(trade["entry_time"]).isoformat(),
                "entry_price": entry,
                "stop_price": stop,
                "target_price": target,
                "time_exit": strategy.time_exit,
                "planned_exit_bar": si + 1 + strategy.time_exit - 1,
                "exit_time": pd.Timestamp(trade["exit_time"]).isoformat(),
                "exit_bar": xi,
                "exit_price": exit_price,
                "exit_reason": trade["reason"],
                "initial_stop_distance": distance,
                "gross_R": (exit_price - entry if strategy.direction == "LONG" else entry - exit_price) / distance,
                "risk_R": float(trade["r"]),
                "allocated_risk_fraction": member.weight * portfolio.base_risk,
                "allocated_risk_usd": 100000 * member.weight * portfolio.base_risk,
                "portfolio_open_risk_before": "UNRESOLVED_REFERENCE_ORDER",
                "portfolio_open_risk_after": "UNRESOLVED_REFERENCE_ORDER",
            })

    # Deterministic portfolio-risk timeline over the Python reference trades.
    # It is explicitly a reference reconstruction, not a claim that it equals
    # the unavailable MT5 deal ledger.
    rows.sort(key=lambda x: (x["entry_time"], x["strategy_id"], int(x["trade_number"])))
    active = []
    for row in rows:
        active = [x for x in active if x["exit_time"] > row["entry_time"]]
        before = sum(float(x["allocated_risk_fraction"]) for x in active)
        requested = float(row["allocated_risk_fraction"])
        allocated = min(requested, max(0.0, portfolio.max_open_risk - before))
        row["portfolio_open_risk_before"] = before
        row["portfolio_open_risk_after"] = before + allocated
        row["allocated_risk_fraction"] = allocated
        row["allocated_risk_usd"] = 100000 * allocated
        row["allocation_status"] = "ACCEPT_FULL" if allocated == requested else "ACCEPT_REDUCED" if allocated > 0 else "REJECT_RISK_LIMIT"
        active.append(row)
    rows.sort(key=lambda x: int(x["trade_number"]))
    write_csv("python_portfolio_trades.csv", rows)
    write_csv("python_signal_stream.csv", signals)
    return portfolio, df, features, start, end, rows, signals, counts


def build_mt5_and_comparisons(portfolio, python_rows, signals, counts):
    member_ids = [x.strategy.readable_id for x in portfolio.strategies]
    mt5_rows = [{
        "record_type": "AGGREGATE_SUMMARY", "trade_number": "", "strategy_id": "UNRESOLVED",
        "direction": "48 LONG / 18 SHORT", "entry_time": "UNRESOLVED", "entry_price": "UNRESOLVED",
        "stop_price": "UNRESOLVED", "target_price": "UNRESOLVED", "volume": "UNRESOLVED",
        "exit_time": "UNRESOLVED", "exit_price": "UNRESOLVED", "exit_reason": "UNRESOLVED",
        "commission": "UNRESOLVED", "swap": "UNRESOLVED", "reported_pnl": "-856.43",
        "source": "REAL_MT5_STRATEGY_TESTER_AGGREGATE_EVIDENCE",
        "notes": json.dumps(MT5_SUMMARY, sort_keys=True),
    }]
    for sid in OBSERVED_IDS:
        mt5_rows.append({
            "record_type": "STRATEGY_ID_OBSERVED", "trade_number": "", "strategy_id": sid,
            "direction": "UNRESOLVED", "entry_time": "UNRESOLVED", "entry_price": "UNRESOLVED",
            "stop_price": "UNRESOLVED", "target_price": "UNRESOLVED", "volume": "UNRESOLVED",
            "exit_time": "UNRESOLVED", "exit_price": "UNRESOLVED", "exit_reason": "UNRESOLVED",
            "commission": "UNRESOLVED", "swap": "UNRESOLVED", "reported_pnl": "UNRESOLVED",
            "source": "REAL_MT5_STRATEGY_TESTER_PARTIAL_STRATEGY_ID_EVIDENCE", "notes": "No trade-level row supplied",
        })
    write_csv("mt5_trades_observed.csv", mt5_rows)

    member_rows = []
    for sid in member_ids:
        member_rows.append({
            "strategy_id": sid, "in_python_portfolio": "YES",
            "observed_in_mt5": "YES" if sid in OBSERVED_IDS else "UNRESOLVED",
            "python_trade_count": counts.get(sid, 0),
            "mt5_trade_count": "UNRESOLVED",
            "status": "MEMBER_OBSERVED" if sid in OBSERVED_IDS else "MEMBER_INACTIVE_OR_UNRESOLVED",
        })
    write_csv("portfolio_membership.csv", member_rows)

    fields = ["strategy_id", "direction", "python_entry_time", "mt5_entry_time", "entry_bar_delta",
              "python_entry_price", "mt5_entry_price", "entry_price_delta", "python_stop", "mt5_stop",
              "stop_delta", "python_target", "mt5_target", "target_delta", "python_exit_time",
              "mt5_exit_time", "exit_bar_delta", "python_exit_reason", "mt5_exit_reason",
              "python_risk_usd", "mt5_implied_risk_usd", "status", "notes"]
    comparisons = []
    for row in python_rows:
        comparisons.append({
            "strategy_id": row["strategy_id"], "direction": row["direction"],
            "python_entry_time": row["entry_time"], "mt5_entry_time": "UNRESOLVED",
            "entry_bar_delta": "UNRESOLVED", "python_entry_price": row["entry_price"],
            "mt5_entry_price": "UNRESOLVED", "entry_price_delta": "UNRESOLVED",
            "python_stop": row["stop_price"], "mt5_stop": "UNRESOLVED", "stop_delta": "UNRESOLVED",
            "python_target": row["target_price"], "mt5_target": "UNRESOLVED", "target_delta": "UNRESOLVED",
            "python_exit_time": row["exit_time"], "mt5_exit_time": "UNRESOLVED",
            "exit_bar_delta": "UNRESOLVED", "python_exit_reason": row["exit_reason"],
            "mt5_exit_reason": "UNRESOLVED", "python_risk_usd": row["allocated_risk_usd"],
            "mt5_implied_risk_usd": "UNRESOLVED", "status": "AMBIGUOUS",
            "notes": "MT5 trade-level ledger unavailable; aggregate 66-trade result cannot be matched chronologically.",
        })
    write_csv("trade_comparison.csv", comparisons, fields)

    signal_rows = []
    for s in signals:
        signal_rows.append({**s, "mt5_signal_time": "UNRESOLVED", "mt5_direction": "UNRESOLVED",
                            "status": "UNRESOLVED", "notes": "No MT5 signal/order log supplied."})
    write_csv("signal_equivalence.csv", signal_rows)
    exit_rows = [{"strategy_id": r["strategy_id"], "python_exit_time": r["exit_time"],
                  "mt5_exit_time": "UNRESOLVED", "python_exit_reason": r["exit_reason"],
                  "mt5_exit_reason": "UNRESOLVED", "status": "UNRESOLVED",
                  "notes": "No MT5 trade-level ledger supplied."} for r in python_rows]
    write_csv("exit_equivalence.csv", exit_rows)

    risk_rows, timeline = [], []
    for r in python_rows:
        distance = abs(float(r["entry_price"]) - float(r["stop_price"]))
        allocated = float(r["allocated_risk_fraction"])
        risk_rows.append({
            "strategy_id": r["strategy_id"], "entry_time": r["entry_time"], "equity_at_entry": "REFERENCE_100000",
            "risk_fraction": allocated, "risk_money": float(r["allocated_risk_usd"]),
            "entry_price": r["entry_price"], "stop_price": r["stop_price"], "stop_distance": distance,
            "tick_size": "UNRESOLVED_MT5", "tick_value": "UNRESOLVED_MT5", "volume": "UNRESOLVED_MT5",
            "implied_stop_loss_usd": "UNRESOLVED_MT5", "implied_risk_fraction": "UNRESOLVED_MT5",
            "portfolio_open_risk_before": r["portfolio_open_risk_before"],
            "portfolio_open_risk_after": r["portfolio_open_risk_after"], "status": "PYTHON_REFERENCE_ONLY",
        })
        timeline.append({"timestamp": r["entry_time"], "event": "REFERENCE_ENTRY",
                         "strategy_id": r["strategy_id"], "open_risk_before": r["portfolio_open_risk_before"],
                         "requested_risk": allocated, "allocated_risk": allocated,
                         "open_risk_after": r["portfolio_open_risk_after"], "status": r["allocation_status"]})
    write_csv("risk_sizing_comparison.csv", risk_rows)
    write_csv("portfolio_open_risk_timeline.csv", timeline)

    by_time = defaultdict(list)
    for s in signals:
        by_time[s["signal_time"]].append(s)
    concurrent = []
    for timestamp, group in sorted(by_time.items()):
        if len(group) < 2:
            continue
        requested = sum(float(x["allocated_risk_fraction"]) for x in group)
        accepted = group if requested <= portfolio.max_open_risk else group[:1]
        concurrent.append({
            "timestamp": timestamp,
            "strategy_ids_signaling": ";".join(x["strategy_id"] for x in group),
            "directions": ";".join(x["direction"] for x in group),
            "risk_requested": requested, "risk_available_before": "UNRESOLVED_MT5_STATE",
            "strategies_accepted": ";".join(x["strategy_id"] for x in accepted),
            "strategies_rejected": "" if len(accepted) == len(group) else ";".join(x["strategy_id"] for x in group[1:]),
            "reason": "PYTHON_REFERENCE_DETERMINISTIC_PORTFOLIO_ORDER",
            "open_risk_after": "UNRESOLVED_MT5_STATE",
        })
    write_csv("concurrent_signals.csv", concurrent)


def write_docs(portfolio, python_rows, signals):
    (OUT / "position_ownership_audit.md").write_text(f'''# Position ownership audit

The generated EA associates each entry with `{PORTFOLIO_ID}`, a strategy ID and
strategy-specific magic number. `SQX_HasPosition` and `SQX_ManagePosition`
filter by symbol and that magic number, so the source-level ownership policy
is explicit and a strategy cannot intentionally close another strategy's
magic-matched position.

The MT5 run completed with 66 trades and multiple strategy IDs, but no
trade/deal ledger or position-ticket history was supplied. Cross-strategy
close/SL/TP ownership therefore cannot be empirically verified for January.
Gate: `PARTIAL` pending the MT5 execution CSV or HTML/deal export.
''')
    (OUT / "risk_policy_audit.md").write_text(f'''# Portfolio risk policy audit

The frozen portfolio contains {len(portfolio.strategies)} members and weights
sum to {sum(x.weight for x in portfolio.strategies):.12f}. The generated MQL5
policy requests `base_risk × strategy_weight`, i.e. 1% is the total weighted
portfolio budget, not 1% per strategy. The common risk manager compares the
requested risk with remaining `max_open_risk` capacity and passes the reduced
risk into volume sizing.

The Python reference ledger contains {len(python_rows)} independently
replayed strategy trades. The MT5 ledger supplied only aggregate PnL and trade
counts, so actual volume, tick value, equity-at-entry and open-risk-before/
after cannot be reconstructed. No claim of empirical 2% compliance is made.
''')
    gates = {
        "MQL5_COMPILE": "PASS", "PORTFOLIO_RUNTIME": "PASS",
        "PORTFOLIO_MEMBERSHIP": "PARTIAL", "SIGNAL_EQUIVALENCE": "UNRESOLVED",
        "ENTRY_TIMING_EQUIVALENCE": "UNRESOLVED", "ENTRY_PRICE_EQUIVALENCE": "UNRESOLVED",
        "STOP_LOGIC_EQUIVALENCE": "UNRESOLVED", "STOP_PRICE_EQUIVALENCE": "UNRESOLVED",
        "TARGET_LOGIC_EQUIVALENCE": "UNRESOLVED", "TARGET_PRICE_EQUIVALENCE": "UNRESOLVED",
        "TIME_EXIT_EQUIVALENCE": "UNRESOLVED", "EXIT_REASON_EQUIVALENCE": "UNRESOLVED",
        "EXIT_BAR_EQUIVALENCE": "UNRESOLVED", "POSITION_OWNERSHIP": "PARTIAL",
        "ACCOUNT_MODE_COMPATIBILITY": "UNRESOLVED", "RISK_SIZING_EQUIVALENCE": "UNRESOLVED",
        "BASE_RISK_SEMANTICS": "PASS", "MAX_OPEN_RISK_ENFORCEMENT": "PARTIAL",
        "CONCURRENT_SIGNAL_HANDLING": "PASS", "COST_MODEL_EQUIVALENCE": "PARTIAL",
        "DATA_FEED_EQUIVALENCE": "UNRESOLVED",
    }
    (OUT / "equivalence_gates.json").write_text(json.dumps(gates, indent=2) + "\n")
    (OUT / "final_report.md").write_text(f'''# SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2

## Evidence status

Python reference trades: **{len(python_rows)}** across the 20 frozen members.
MT5 trades: **66 aggregate only**; 132 deals, 48 long and 18 short. No
trade-level MT5 CSV, HTML or execution log exists in the repository.

Matched: **not determinable**. Python-only and MT5-only: **not determinable**.
Trade comparison rows are retained as `AMBIGUOUS`, never as fabricated
matches. Fourteen observed strategy IDs are confirmed portfolio members; six
members are `UNRESOLVED` between inactive and missing evidence.

Portfolio runtime: **PASS**. The tester completed with no runtime crash.
MQL5 compilation: **PASS** from the external MetaEditor evidence.

The source audit confirms deterministic S0→S19 evaluation, weighted base-risk
semantics (`1% × strategy weight`) and magic-number ownership filters. Actual
January signal, exit, volume and 2% open-risk equivalence cannot be certified
without the MT5 trade/deal ledger and signal/order log.

## Required next evidence

Export from MT5 Strategy Tester the deal/order report or `SQX_execution.csv`
with timestamp, strategy ID/comment, magic, direction, volume, entry/exit,
SL/TP, retcode, balance/equity and open risk. Also export the account mode
(HEDGING or NETTING) and EURUSD H1 OHLC/tick data used by the tester.

Decision: `BLOCKED_ON_MT5_EVIDENCE`
''')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    portfolio, _, _, _, _, rows, signals, counts = build_python()
    build_mt5_and_comparisons(portfolio, rows, signals, counts)
    write_docs(portfolio, rows, signals)
    print(json.dumps({"python_trades": len(rows), "python_signals": len(signals),
                      "mt5_aggregate_trades": 66, "observed_ids": len(OBSERVED_IDS),
                      "out": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
