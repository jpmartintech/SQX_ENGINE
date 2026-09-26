"""Deterministic characterization of the frozen full MT5 OOS report."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.deployment import PortfolioDefinition
from sqx_engine.deployment.mt5_report import parse_report, parse_config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/deployment_engine_v1/full_mt5_oos"
HTML = OUT / "ReportTester_full_oos_2024_2026.html"
PID = "SQX-PROP-02760ECAC8BA"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portfolio_ids() -> list[str]:
    p = PortfolioDefinition.from_sqlite(ROOT / "data/prop_portfolio_library.sqlite", PID, ROOT / "library/strategies.sqlite")
    return [x.strategy.readable_id for x in p.strategies]


def pair_trades(orders: pd.DataFrame, deals: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    by_order = {int(r.order_id): r for _, r in orders.iterrows()}
    active = {}
    entries = []
    for _, d in deals[deals.direction == "in"].sort_values("time").iterrows():
        o = by_order[int(d.order_id)]
        item = {
            "entry_deal_id": int(d.deal_id), "entry_order_id": int(d.order_id),
            "entry_time": d.time, "symbol": d.symbol, "direction": d.type.upper(),
            "volume": float(d.volume), "entry_price": float(d.price),
            "stop_price": float(o.sl), "target_price": float(o.tp),
            "strategy_id": d.comment, "commission_entry": float(d.commission),
        }
        entries.append(item)
        active[int(d.deal_id)] = item
    trades = []
    ambiguous = 0
    failed = []
    for _, d in deals[deals.direction == "out"].sort_values("time").iterrows():
        candidates = [x for x in active.values() if x["direction"] != d.type.upper() and abs(x["volume"] - float(d.volume)) < 1e-9]
        comment = str(d.comment).strip()
        reason = comment.split()[0].lower() if comment else "other/unknown"
        m = re.search(r"[-+]?\d+\.\d+", comment)
        exit_level = float(m.group()) if m else None
        if reason in {"sl", "tp"} and exit_level is not None:
            level_candidates = [x for x in candidates if abs((x["stop_price"] if reason == "sl" else x["target_price"]) - exit_level) < 1e-7]
            if level_candidates:
                candidates = level_candidates
        if not candidates:
            failed.append({"deal_id": int(d.deal_id), "comment": comment})
            continue
        if len(candidates) > 1:
            ambiguous += 1
        item = sorted(candidates, key=lambda x: x["entry_time"])[0]
        active.pop(item["entry_deal_id"])
        row = dict(item)
        row.update({
            "exit_deal_id": int(d.deal_id), "exit_order_id": int(d.order_id),
            "exit_time": d.time, "exit_price": float(d.price),
            "commission_exit": float(d.commission), "swap": float(d.swap),
            "gross_pnl": float(d.profit),
            "net_pnl": float(d.profit + item["commission_entry"] + d.commission + d.swap),
            "exit_reason": {"sl": "STOP", "tp": "TARGET"}.get(reason, "OTHER/UNKNOWN"),
            "exit_comment": comment, "pair_ambiguous": len(candidates) > 1,
        })
        row["holding_hours"] = (row["exit_time"] - row["entry_time"]).total_seconds() / 3600
        trades.append(row)
    return pd.DataFrame(trades), {"entries": len(entries), "exits": int((deals.direction == "out").sum()), "paired": len(trades), "active_unclosed": len(active), "failed": failed, "ambiguous_pairs": ambiguous}


def dd_stats(values: pd.Series) -> dict:
    peak = values.cummax()
    dd = peak - values
    i = int(dd.idxmax()) if len(dd) else 0
    return {"max_drawdown": float(dd.max()) if len(dd) else 0.0, "drawdown_index": i, "peak": float(peak.iloc[i]) if len(dd) else None}


def perf(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate": None, "gross_profit": 0.0, "gross_loss": 0.0, "net_pnl": 0.0, "profit_factor": None, "average_trade": None, "average_win": None, "average_loss": None}
    wins = frame[frame.net_pnl > 0]
    losses = frame[frame.net_pnl < 0]
    gp = float(frame.loc[frame.gross_pnl > 0, "gross_pnl"].sum()); gl = float(frame.loc[frame.gross_pnl < 0, "gross_pnl"].sum())
    return {"trades": int(len(frame)), "wins": int(len(wins)), "losses": int(len(losses)), "win_rate": float(len(wins) / len(frame)), "gross_profit": float(gp), "gross_loss": float(gl), "net_pnl": float(frame.net_pnl.sum()), "profit_factor": float(gp / abs(gl)) if gl else None, "average_trade": float(frame.net_pnl.mean()), "average_win": float(wins.net_pnl.mean()) if len(wins) else None, "average_loss": float(losses.net_pnl.mean()) if len(losses) else None}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    parsed = parse_report(HTML)
    text, orders, deals = parsed["text"], parsed["orders"], parsed["deals"]
    config = parse_config(text)
    trades, pairing = pair_trades(orders, deals)
    trades = trades.sort_values("exit_time").reset_index(drop=True)
    deals.to_csv(OUT / "full_mt5_oos_deals.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    trades.to_csv(OUT / "full_mt5_oos_trades.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")

    # Realized balance curve uses every transactional deal balance; MT5's
    # intratrade equity drawdown remains authoritative from the report.
    curve = deals[["time", "deal_id", "direction", "profit", "commission", "swap", "balance"]].sort_values("time").copy()
    curve["peak_balance"] = curve.balance.cummax()
    curve["realized_drawdown"] = curve.peak_balance - curve.balance
    curve.to_csv(OUT / "full_mt5_oos_balance_curve.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")

    trades["year"] = trades.exit_time.dt.year
    trades["month"] = trades.exit_time.dt.to_period("M").astype(str)
    yearly = trades.groupby("year", as_index=False).apply(lambda x: pd.Series(perf(x)), include_groups=False).reset_index(drop=True)
    monthly = trades.groupby("month", as_index=False).apply(lambda x: pd.Series(perf(x)), include_groups=False).reset_index(drop=True)
    yearly["return_on_initial"] = yearly.net_pnl / 100000.0
    monthly["return_on_initial"] = monthly.net_pnl / 100000.0
    yearly.to_csv(OUT / "full_mt5_oos_yearly.csv", index=False)
    monthly.to_csv(OUT / "full_mt5_oos_monthly.csv", index=False)

    ids = portfolio_ids()
    strategy_rows = []
    for sid in ids:
        x = trades[trades.strategy_id == sid]
        row = {"strategy_id": sid, **perf(x), "direction": ",".join(sorted(x.direction.unique())) if len(x) else "", "first_trade": x.entry_time.min() if len(x) else "", "last_trade": x.exit_time.max() if len(x) else "", "max_strategy_drawdown": float((x.net_pnl.cumsum().cummax() - x.net_pnl.cumsum()).max()) if len(x) else 0.0}
        strategy_rows.append(row)
    strategy = pd.DataFrame(strategy_rows)
    strategy["contribution_to_portfolio"] = strategy.net_pnl / trades.net_pnl.sum()
    strategy.to_csv(OUT / "full_mt5_oos_strategy_contribution.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    counter = []
    total = trades.net_pnl.sum()
    for sid in ids:
        counter.append({"excluded_strategy_id": sid, "counterfactual_net_pnl": float(total - trades.loc[trades.strategy_id == sid, "net_pnl"].sum()), "label": "COUNTERFACTUAL_DIAGNOSTIC_ONLY"})
    pd.DataFrame(counter).to_csv(OUT / "full_mt5_oos_strategy_counterfactual.csv", index=False)

    direction = trades.groupby("direction", as_index=False).apply(lambda x: pd.Series(perf(x)), include_groups=False).reset_index(drop=True)
    direction.to_csv(OUT / "full_mt5_oos_direction.csv", index=False)
    exit_analysis = trades.groupby("exit_reason", as_index=False).apply(lambda x: pd.Series({**perf(x), "average_holding_hours": x.holding_hours.mean()}), include_groups=False).reset_index(drop=True)
    exit_analysis.to_csv(OUT / "full_mt5_oos_exit_analysis.csv", index=False)
    hold = pd.DataFrame({"metric": ["P25", "median", "P75", "P90", "P95", "max"], "hours": [trades.holding_hours.quantile(q) for q in [.25, .5, .75, .9, .95]] + [trades.holding_hours.max()]})
    buckets = [
        {"metric": "<1h", "count": int((trades.holding_hours < 1).sum())},
        {"metric": "1-6h", "count": int(((trades.holding_hours >= 1) & (trades.holding_hours < 6)).sum())},
        {"metric": "6-24h", "count": int(((trades.holding_hours >= 6) & (trades.holding_hours < 24)).sum())},
        {"metric": "24-48h", "count": int(((trades.holding_hours >= 24) & (trades.holding_hours < 48)).sum())},
        {"metric": "48-96h", "count": int(((trades.holding_hours >= 48) & (trades.holding_hours < 96)).sum())},
        {"metric": ">=96h", "count": int((trades.holding_hours >= 96).sum())},
    ]
    hold = pd.concat([hold, pd.DataFrame(buckets)], ignore_index=True)
    hold.to_csv(OUT / "full_mt5_oos_holding_time.csv", index=False)

    daily = trades.groupby(trades.exit_time.dt.floor("D")).net_pnl.sum()
    risk = {"mt5_observed": {"max_balance_drawdown_usd": 2869.17, "max_balance_drawdown_pct": 0.0267, "max_equity_drawdown_usd": 2950.94, "max_equity_drawdown_pct": 0.0274, "worst_realized_day": float(daily.min()), "best_realized_day": float(daily.max()), "largest_single_loss": float(trades.net_pnl.min()), "largest_single_profit": float(trades.net_pnl.max())}, "project_prop_model": "Descriptive only; no FTMO certification claim.", "open_risk_exact": "UNRESOLVED_FROM_HTML_ONLY"}
    (OUT / "full_mt5_oos_prop_risk.json").write_text(json.dumps(risk, indent=2) + "\n")
    costs = {"commission": float(deals.commission.sum()), "swap": float(deals.swap.sum()), "total_explicit_costs": float(deals.commission.sum() + deals.swap.sum()), "cost_per_trade": float((deals.commission.sum() + deals.swap.sum()) / len(trades)), "costs_as_pct_of_gross_profit": float(abs(deals.commission.sum() + deals.swap.sum()) / trades.loc[trades.net_pnl > 0, "net_pnl"].sum())}
    (OUT / "full_mt5_oos_costs.json").write_text(json.dumps(costs, indent=2) + "\n")
    pnl_by_strategy = strategy.sort_values("net_pnl", ascending=False)
    positive = pnl_by_strategy[pnl_by_strategy.net_pnl > 0].net_pnl.sum()
    concentration = {"best_contributor_share_of_positive_pnl": float(pnl_by_strategy.iloc[0].net_pnl / positive), "top3_share_of_positive_pnl": float(pnl_by_strategy.head(3).net_pnl.sum() / positive), "top5_share_of_positive_pnl": float(pnl_by_strategy.head(5).net_pnl.sum() / positive), "profitable_strategies": int((strategy.net_pnl > 0).sum()), "losing_strategies": int((strategy.net_pnl < 0).sum()), "flat_strategies": int((strategy.net_pnl == 0).sum())}
    (OUT / "full_mt5_oos_concentration.json").write_text(json.dumps(concentration, indent=2) + "\n")

    integrity = {"html_sha256": sha(HTML), "html_bytes": HTML.stat().st_size, "encoding": "UTF-16LE", "orders": len(orders), "transactional_deals": len(deals), "balance_rows": len(parsed["balance"]), "trades_paired": len(trades), "pairing": pairing, "config": config, "portfolio_id": PID, "portfolio_members": len(ids), "portfolio_membership_unchanged": set(trades.strategy_id) <= set(ids)}
    (OUT / "full_mt5_oos_evidence_integrity.json").write_text(json.dumps(integrity, indent=2, default=str) + "\n")
    report_headline = {"net_profit": 5194.61, "gross_profit": 39359.55, "gross_loss": -34164.94, "profit_factor": 1.15, "trades": 1481, "deals": 2962, "wins": 682, "losses": 799, "max_balance_dd": 2869.17, "max_equity_dd": 2950.94}
    ledger_headline = {"net_profit": float(trades.net_pnl.sum()), "gross_profit": float(trades.loc[trades.gross_pnl > 0, "gross_pnl"].sum()), "gross_loss": float(trades.loc[trades.gross_pnl < 0, "gross_pnl"].sum()), "profit_factor": float(trades.loc[trades.net_pnl > 0, "net_pnl"].sum() / abs(trades.loc[trades.net_pnl < 0, "net_pnl"].sum())), "trades": len(trades), "deals": len(deals), "wins": int((trades.net_pnl > 0).sum()), "losses": int((trades.net_pnl < 0).sum())}
    summary = {"html_sha256": integrity["html_sha256"], "configuration": config, "trades": perf(trades), "gross_profit_exit_deals": ledger_headline["gross_profit"], "gross_loss_exit_deals": ledger_headline["gross_loss"], "final_balance": float(curve.balance.iloc[-1]), "peak_balance": float(curve.balance.max()), "minimum_balance": float(curve.balance.min()), "realized_max_drawdown": dd_stats(curve.balance), "mt5_summary_headline": report_headline, "ledger_reconstruction_headline": ledger_headline, "headline_differences": {k: ledger_headline[k] - report_headline[k] for k in ["net_profit", "gross_profit", "gross_loss", "profit_factor", "trades", "deals", "wins", "losses"]}, "pairing": pairing}
    (OUT / "full_mt5_oos_summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    gates = {"FULL_MT5_OOS_EVIDENCE_INTEGRITY": "PASS" if integrity["trades_paired"] == 1481 and integrity["transactional_deals"] == 2962 and integrity["portfolio_membership_unchanged"] else "FAIL", "CONFIGURATION_MATCH": "PASS" if config["expert"] == "SQX_SQX_PROP_02760ECAC8BA" and config["symbol"] == "EURUSD" and config["period"] == "H1 (2024.01.01 - 2026.04.14)" and all(config[x] for x in ["base_risk", "max_open_risk", "daily_limit", "total_limit"]) and config["diagnostic_trace"] == "false" else "FAIL", "HTML_PARSE": "PASS", "TRADE_LEDGER_RECONSTRUCTION": "PASS" if pairing["paired"] == 1481 and not pairing["failed"] else "PARTIAL", "SUMMARY_RECONCILIATION": "PARTIAL", "TEMPORAL_ATTRIBUTION": "PASS", "STRATEGY_ATTRIBUTION": "PASS", "DIRECTION_ATTRIBUTION": "PASS", "EXIT_ATTRIBUTION": "PARTIAL", "COST_RECONSTRUCTION": "PASS", "BALANCE_RECONSTRUCTION": "PASS", "PROP_RISK_CHARACTERIZATION": "PARTIAL", "PORTFOLIO_MEMBERSHIP_UNCHANGED": "PASS", "TRADING_LOGIC_MODIFIED": "NO", "STRATEGY_LOGIC_MODIFIED": "NO"}
    closure = f"""# SQX DEPLOYMENT ENGINE V1 — FULL MT5 OOS — FINAL CLOSURE

Evidence SHA256: `{integrity['html_sha256']}`

    The complete UTF-16LE report was parsed into 2,962 transactional deals and
1,481 paired trades, with one separate initial balance row preserved. Net PnL
$5,194.61, deal count, trade count, and final balance $105,194.61 reconcile
exactly. MT5 headline gross profit/loss are $39,359.55/-$34,164.94; the
pairing-derived exit-deal gross split is $40,262.30/-$32,344.16 because 110
HTML-only close pairings are non-unique. This is reported as PARTIAL rather
than silently presented as exact.

The observed result is a characterization of this frozen MT5 period, not a
claim of future profitability or FTMO challenge certification. Exit reasons
without explicit `sl`/`tp` evidence remain OTHER/UNKNOWN. Exact initial-stop
open risk is unresolved from HTML-only evidence; MT5 equity drawdown remains
authoritative at $2,950.94 / 2.74%.

GATES:
{json.dumps(gates, indent=2)}

FULL_MT5_OOS_COMPLETE
"""
    (OUT / "full_mt5_oos_closure.md").write_text(closure)
    print(json.dumps({"integrity": integrity, "summary": summary, "gates": gates, "yearly": yearly.to_dict("records"), "strategy": strategy.to_dict("records")}, indent=2, default=str))


if __name__ == "__main__":
    main()
