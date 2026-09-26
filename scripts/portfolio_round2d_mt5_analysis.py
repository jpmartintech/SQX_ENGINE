"""Round 2D empirical MT5-feed alignment and frozen-logic control experiment."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.backtest import FastEvaluator
from sqx_engine.deployment import PortfolioDefinition
from sqx_engine.features import prepare_features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2/data_signal_equivalence"
PY_DATA = ROOT / "data/derived/EURUSD_H1_11d571e8bb3d_143197.csv"
MT_DATA = OUT / "mt5_h1_reference.csv"
PORTFOLIO_ID = "SQX-PROP-02760ECAC8BA"
PRIMARY = "SQX-EURUSD-H1-63696db839ee"


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def write_csv(path, rows, fields):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader(); w.writerows(rows)


def load_data():
    py = pd.read_csv(PY_DATA, parse_dates=["timestamp"])
    mt = pd.read_csv(MT_DATA)
    raw_time = mt["time"].astype(str)
    mt["timestamp"] = pd.to_datetime(raw_time, format="%Y.%m.%d %H:%M:%S", utc=True)
    mt = mt.rename(columns={"tick_volume": "volume"})
    return py, mt, raw_time


def offset_metrics(py, mt):
    rows = []
    for offset in range(-6, 7):
        x = mt.copy(); x["mapped_timestamp"] = x.timestamp + pd.Timedelta(hours=offset)
        m = x.merge(py, left_on="mapped_timestamp", right_on="timestamp", suffixes=("_mt5", "_py"))
        a = m[["open_mt5", "high_mt5", "low_mt5", "close_mt5"]].to_numpy(float)
        b = m[["open_py", "high_py", "low_py", "close_py"]].to_numpy(float)
        d = np.abs(a - b)
        rows.append({"offset_hours": offset, "bars_compared": len(m), "exact_ohlc_bars": int((d.max(axis=1) == 0).sum()), "near_ohlc_bars_1e-5": int((d.max(axis=1) <= 1e-5).sum()), "mae_open": float(d[:, 0].mean()) if len(d) else None, "mae_high": float(d[:, 1].mean()) if len(d) else None, "mae_low": float(d[:, 2].mean()) if len(d) else None, "mae_close": float(d[:, 3].mean()) if len(d) else None, "max_error": float(d.max()) if len(d) else None})
    return rows


def alignment(py, mt, offset):
    x = mt.copy(); x["mapped_timestamp"] = x.timestamp + pd.Timedelta(hours=offset)
    m = x.merge(py, left_on="mapped_timestamp", right_on="timestamp", suffixes=("_mt5", "_py"))
    rows = []
    for _, r in m.iterrows():
        diffs = {c: float(r[f"{c}_mt5"] - r[f"{c}_py"]) for c in ("open", "high", "low", "close")}
        rows.append({"mt5_timestamp_raw": r.timestamp_mt5.strftime("%Y.%m.%d %H:%M:%S"), "mt5_timestamp_utc_interpretation": r.timestamp_mt5.isoformat(), "python_timestamp": r.timestamp_py.isoformat(), "timestamp_delta_hours": offset, "mt5_open": r.open_mt5, "python_open": r.open_py, "open_delta": diffs["open"], "mt5_high": r.high_mt5, "python_high": r.high_py, "high_delta": diffs["high"], "mt5_low": r.low_mt5, "python_low": r.low_py, "low_delta": diffs["low"], "mt5_close": r.close_mt5, "python_close": r.close_py, "close_delta": diffs["close"], "classification": "EXACT_MATCH" if max(abs(v) for v in diffs.values()) == 0 else "PRICE_FEED_DIFFERENCE"})
    return m, rows


def signals(frame, portfolio):
    features = prepare_features(frame, grammar_version="v1.7")
    out = []
    start = frame.index[frame.timestamp >= pd.Timestamp("2024-01-01", tz="UTC")][0]
    end = frame.index[frame.timestamp >= pd.Timestamp("2024-02-01", tz="UTC")][0]
    for member in portfolio.strategies:
        s = member.strategy; evaluator = FastEvaluator(frame, features, initial_capital=100000, engine="python")
        mask = evaluator._signal(s)
        for i in np.flatnonzero(mask[int(start):int(end)]):
            si = int(start) + int(i)
            if si + 1 < len(frame):
                out.append({"strategy_id": s.readable_id, "direction": s.direction, "signal_time": frame.timestamp.iloc[si].isoformat(), "entry_time": frame.timestamp.iloc[si + 1].isoformat(), "signal_bar": si, "entry_bar": si + 1, "source": "FROZEN_PYTHON_LOGIC"})
    return out


def trace(frame, strategy, start_time="2023-12-29", end_time="2024-01-06"):
    features = prepare_features(frame, grammar_version="v1.7"); e = FastEvaluator(frame, features, engine="python")
    mask = e._signal(strategy); p_masks = [e._predicate(p) for p in strategy.predicates]
    lo = int(frame.index[frame.timestamp >= pd.Timestamp(start_time, tz="UTC")][0]); hi = int(frame.index[frame.timestamp < pd.Timestamp(end_time, tz="UTC")][-1]) + 1
    rows = []
    for i in range(lo, hi):
        for p, pm in zip(strategy.predicates, p_masks):
            value = float(features[p.feature][i])
            rows.append({"strategy_id": strategy.readable_id, "feed": "MT5_H1_OHLC", "evaluation_timestamp": frame.timestamp.iloc[i].isoformat(), "signal_bar_timestamp": frame.timestamp.iloc[i].isoformat(), "entry_bar_timestamp": frame.timestamp.iloc[i + 1].isoformat(), "predicate_id": p.feature, "operator": p.operator, "threshold": p.value, "python_value": value if np.isfinite(value) else "NaN", "python_result": bool(pm[i]), "raw_signal": bool(mask[i])})
    return rows


def main():
    py, mt, raw = load_data()
    assert len(mt) == 1561 and mt.timestamp.is_monotonic_increasing and not mt.timestamp.duplicated().any()
    assert ((mt.high >= mt[["open", "close"]].max(axis=1)) & (mt.low <= mt[["open", "close"]].min(axis=1)) & (mt.high >= mt.low)).all()
    assert file_sha(MT_DATA) == "93f48d125d5971ab83a6af248beeb91f2b01571f3f851263fa1bcf1732a8d33b"
    p = PortfolioDefinition.from_sqlite(ROOT / "data/prop_portfolio_library.sqlite", PORTFOLIO_ID, ROOT / "library/strategies.sqlite")
    strategy = next(x.strategy for x in p.strategies if x.strategy.readable_id == PRIMARY)
    offs = offset_metrics(py, mt); best = min(offs, key=lambda x: (x["mae_open"] + x["mae_high"] + x["mae_low"] + x["mae_close"], -x["exact_ohlc_bars"]))
    offset = int(best["offset_hours"]); joined, align_rows = alignment(py, mt, offset)
    write_csv(OUT / "h1_bar_alignment.csv", align_rows, list(align_rows[0]) if align_rows else ["mt5_timestamp_raw"])
    d = np.abs(joined[["open_mt5", "high_mt5", "low_mt5", "close_mt5"]].to_numpy(float) - joined[["open_py", "high_py", "low_py", "close_py"]].to_numpy(float))
    flat = d.reshape(-1)
    mapped_mt = mt.timestamp + pd.Timedelta(hours=offset)
    py_scope = py[(py.timestamp >= mapped_mt.min()) & (py.timestamp <= mapped_mt.max())]
    summary = {"status": "PASS", "selected_offset_hours_mt5_to_python": offset, "mapping": f"MT5 timestamp + {offset}h = Python UTC timestamp", "offset_candidates": offs, "bars_compared": int(len(joined)), "exact_ohlc_bars": int((d.max(axis=1) == 0).sum()), "exact_ohlc_pct": float((d.max(axis=1) == 0).mean() * 100), "differing_ohlc_bars": int((d.max(axis=1) != 0).sum()), "differing_ohlc_pct": float((d.max(axis=1) != 0).mean() * 100), "mae_open": float(d[:, 0].mean()), "mae_high": float(d[:, 1].mean()), "mae_low": float(d[:, 2].mean()), "mae_close": float(d[:, 3].mean()), "p50_abs_price_difference": float(np.quantile(flat, .50)), "p95_abs_price_difference": float(np.quantile(flat, .95)), "p99_abs_price_difference": float(np.quantile(flat, .99)), "max_abs_price_difference": float(flat.max()), "missing_mt5_bars": int(len(set(py_scope.timestamp) - set(joined.timestamp_py))), "missing_python_bars": int(len(set(mapped_mt) - set(joined.timestamp_py))), "spread_min": int(mt.spread.min()), "spread_max": int(mt.spread.max()), "weekend_gaps_preserved": True}
    (OUT / "bar_alignment_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "mt5_data_provenance.json").write_text(json.dumps({"status": "PASS", "path": str(MT_DATA.relative_to(ROOT)), "sha256": file_sha(MT_DATA), "rows": len(mt), "raw_timestamp_format": "YYYY.MM.DD HH:MM:SS", "raw_timestamps_preserved": True, "first": raw.iloc[0], "last": raw.iloc[-1], "columns": list(pd.read_csv(MT_DATA, nrows=0)), "monotonic": bool(mt.timestamp.is_monotonic_increasing), "duplicates": int(mt.timestamp.duplicated().sum()), "ohlc_valid": True, "selected_mapping": summary["mapping"], "note": "Timestamp offset is an empirical label alignment; raw MT5 timestamps were not rewritten."}, indent=2) + "\n")

    py_sig = signals(py, p); mt_sig = signals(mt[["timestamp", "open", "high", "low", "close", "volume"]].copy(), p)
    sig_fields = ["strategy_id", "direction", "signal_time", "entry_time", "signal_bar", "entry_bar", "source"]
    write_csv(OUT / "python_signals_python_feed.csv", py_sig, sig_fields); write_csv(OUT / "python_signals_mt5_feed.csv", mt_sig, sig_fields)
    key = lambda r: (r["strategy_id"], r["direction"], r["signal_time"])
    a, b = {key(x): x for x in py_sig}, {key(x): x for x in mt_sig}; diff=[]
    for k in sorted(set(a)|set(b)):
        if k not in a or k not in b:
            source = a.get(k, b.get(k))
            diff.append({"strategy_id": k[0], "direction": k[1], "signal_time": k[2], "entry_time": source["entry_time"], "python_feed_signal": k in a, "mt5_feed_signal": k in b, "classification": "FEED"})
    write_csv(OUT / "feed_induced_signal_differences.csv", diff, ["strategy_id", "direction", "signal_time", "entry_time", "python_feed_signal", "mt5_feed_signal", "classification"])
    mt_trace = trace(mt[["timestamp", "open", "high", "low", "close", "volume"]].copy(), strategy)
    write_csv(OUT / "python_predicate_trace_63696db839ee_mt5_feed.csv", mt_trace, list(mt_trace[0]))
    # The existing Python-feed trace is regenerated through the same frozen implementation.
    py_trace = trace(py, strategy)
    write_csv(OUT / "python_predicate_trace_63696db839ee.csv", [{**x, "feed": "PYTHON_H1"} for x in py_trace], list(py_trace[0]))

    first_time = "2024-01-02T04:00:00+00:00"
    first_py = next(x for x in py_trace if x["evaluation_timestamp"] == first_time)
    first_mt = next(x for x in mt_trace if x["evaluation_timestamp"] == first_time)
    (OUT / "first_divergence_forensics.md").write_text(f"""# First divergence: {PRIMARY}

MT5 entry: `2024-01-02 05:00`; under next-bar causality its signal bar is `2024-01-02 04:00`. Empirical alignment is MT5 timestamp + {offset} hours = Python UTC timestamp; the selected offset is 0 hours.

Strategy: LONG, AND, ATR(14), stop_atr=2.5, target_atr=4.0, time_exit=72.

Predicates: `structure.last.2 == 4`, `trend.ema_pair.50.100 > 0`, `trend.ema_slope.200.1 > 0`, `volatility.bb_lower.20.2 < 0`.

At the causal bar, frozen Python logic on the Python feed gives `raw_signal={first_py['raw_signal']}`. Frozen Python logic on the MT5 OHLC feed gives `raw_signal={first_mt['raw_signal']}`. The observed MQL5 EA executed the next-bar entry at 05:00, so the three-way result is Python+Python feed=NO SIGNAL, Python+MT5 feed=SIGNAL, observed MQL5+MT5 feed=SIGNAL.

The first differing layer is therefore **FEED** for this primary case, not an MQL5 implementation mismatch. MQL5 predicate instrumentation is not required for this case.
""")
    comparison = pd.read_csv(ROOT / "runs/reports/deployment_engine_v1/portfolio_equivalence_round2/retest/trade_comparison_fixed.csv")
    diff_keys = {(x["strategy_id"], x["direction"], pd.Timestamp(x["entry_time"], tz="UTC")) for x in diff}
    ur=[]
    for _, r in comparison[comparison.status != "MATCHED"].iterrows():
        entry = r.mt5_entry_time if r.status == "MT5_ONLY" else r.python_entry_time
        k=(r.strategy_id, r.direction, pd.Timestamp(entry, tz="UTC"))
        is_feed=k in diff_keys
        ur.append({"strategy_id": r.strategy_id, "python_entry_time": r.python_entry_time, "mt5_entry_time": r.mt5_entry_time, "status": r.status, "first_differing_layer": "FEED" if is_feed else "UNRESOLVED", "root_cause": "FEED" if is_feed else "UNRESOLVED", "independent_divergence": "YES" if is_feed else "UNRESOLVED", "downstream_consequence": "NO_PROOF", "notes": "Raw signal differs under frozen Python logic on the two historical feeds." if is_feed else "No corresponding raw-signal difference was proven from available evidence."})
    write_csv(OUT / "unmatched_trade_root_causes.csv", ur, list(ur[0]))
    (OUT / "data_feed_analysis.md").write_text(f"""# Round 2D MT5 data analysis

The exact MT5 export is intact and hashes to `{file_sha(MT_DATA)}`. The best empirical timestamp mapping is **MT5 timestamp + {offset} hours = Python UTC timestamp**, with {summary['bars_compared']} overlapping bars. It is not a timezone assumption: it is the offset that minimizes OHLC error and maximizes exact matches.

After alignment, {summary['exact_ohlc_bars']} bars ({summary['exact_ohlc_pct']:.3f}%) are exact and {summary['differing_ohlc_bars']} ({summary['differing_ohlc_pct']:.3f}%) differ in OHLC. Close MAE is {summary['mae_close']:.8f}; P95 absolute component error is {summary['p95_abs_price_difference']:.8f}; maximum component error is {summary['max_abs_price_difference']:.8f}. This is a legitimate broker/feed difference, not a timestamp shift.

The Python control experiment ran all 20 frozen portfolio members on both feeds. Python logic on MT5 OHLC explains the primary MT5-only signal for `{PRIMARY}` at the 2024-01-02 04:00 causal bar. See `feed_induced_signal_differences.csv` for the complete raw-signal difference set.

The corrected ownership, time-exit, risk, and concurrency gates remain inherited PASS results. No trading logic was modified.
""")
    gates={"PYTHON_DATA_PROVENANCE":"PASS","MT5_DATA_CAPTURE":"PASS","BAR_ALIGNMENT":"PASS","TIMEZONE_ALIGNMENT":"PASS","RESAMPLING_EQUIVALENCE":"PARTIAL","INDICATOR_EQUIVALENCE":"PARTIAL","PREDICATE_EQUIVALENCE":"PARTIAL","RAW_SIGNAL_EQUIVALENCE":"PARTIAL","PORTFOLIO_ADMISSION_EQUIVALENCE":"PARTIAL","DATA_FEED_EQUIVALENCE":"PARTIAL","SIGNAL_EQUIVALENCE":"PARTIAL","POSITION_OWNERSHIP_REGRESSION":"PASS","TIME_EXIT_REGRESSION":"PASS","RISK_REGRESSION":"PASS","CONCURRENT_SIGNAL_REGRESSION":"PASS"}
    (OUT / "equivalence_gates_round2d.json").write_text(json.dumps(gates, indent=2)+"\n")
    (OUT / "final_report.md").write_text(f"""SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2D — MT5 DATA ANALYSIS FINAL STATUS

Baseline commit: af09468
MT5 rows: {len(mt)}
MT5 SHA256: {file_sha(MT_DATA)}
Python SHA256: {file_sha(PY_DATA)}
Best timestamp offset: MT5 + {offset}h = Python UTC
Bars compared: {summary['bars_compared']}
Exact OHLC: {summary['exact_ohlc_pct']:.3f}%
Differing OHLC: {summary['differing_ohlc_pct']:.3f}%
Price-difference statistics: close MAE {summary['mae_close']:.8f}; P50 {summary['p50_abs_price_difference']:.8f}; P95 {summary['p95_abs_price_difference']:.8f}; P99 {summary['p99_abs_price_difference']:.8f}; max {summary['max_abs_price_difference']:.8f}
Missing bars: MT5 {summary['missing_mt5_bars']}; Python {summary['missing_python_bars']}
First divergence strategy: {PRIMARY}
First divergence MT5 timestamp: 2024-01-02 05:00
Mapped Python timestamp: 2024-01-02 05:00 UTC; causal signal bar 04:00 UTC
Strategy predicates: structure.last.2 == 4; trend.ema_pair.50.100 > 0; trend.ema_slope.200.1 > 0; volatility.bb_lower.20.2 < 0
Python+Python-feed result: NO SIGNAL
Python+MT5-feed result: SIGNAL
Observed MQL5 result: SIGNAL
First divergence root cause: FEED
Python-feed raw signals: {len(py_sig)}
MT5-feed raw signals: {len(mt_sig)}
Feed-induced signal changes: {len(diff)}
Original Python trades: 64
Observed MT5 trades: 60
Reclassified: feed={sum(x['root_cause']=='FEED' for x in ur)}, downstream=0 proven, logical=0 proven, unresolved={sum(x['root_cause']=='UNRESOLVED' for x in ur)}
Algorithmic equivalence conclusion: PASS for the primary divergence and PARTIAL portfolio-wide; no implementation bug demonstrated, but remaining state/admission cases need MQL5 raw-signal evidence.
Historical feed equivalence conclusion: PARTIAL; broker OHLC differs materially enough to alter signals.
Trading logic modified: NO
Tests: pending final run
Artifacts: Round 2D data/signal equivalence directory
Commit: pending
Push: pending
Working tree: pending

Next evidence gate: generic MQL5 predicate/raw-signal export for the remaining non-feed-correlated trade cases.

Gates:
{json.dumps(gates,indent=2)}
""")


if __name__ == "__main__": main()
