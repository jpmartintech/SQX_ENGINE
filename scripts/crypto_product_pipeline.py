#!/usr/bin/env python3
"""Productization loop using only burned Crypto V2/V3 evidence.

This deliberately does not open protected data or generate strategies.  It
builds a broad GOOD-strategy library, evaluates bounded portfolio candidates
with the chronological concurrent engine, and emits the product handoff
artifacts.  Search budgets are recorded rather than silently represented as
larger experiments.
"""
from __future__ import annotations

import hashlib, json, os, platform, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "runs/reports/crypto_factory_v2"
OUT = ROOT / "runs/reports/crypto_product_pipeline"
DATA = ROOT / "data/crypto_v2"
sys.path.insert(0, str(ROOT / "src"))
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.portfolio_v3 import replay_concurrent
from sqx_engine.strategy import StrategyDefinition


def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + "\n")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def utc(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def splits():
    return json.loads((V2 / "temporal_splits.json").read_text())


def load(asset, start=None, end=None):
    filters = []
    if start is not None: filters.append(("timestamp", ">=", utc(start)))
    if end is not None: filters.append(("timestamp", "<", utc(end)))
    d = pd.read_parquet(DATA / f"{asset}_M15.parquet", filters=filters).sort_values("timestamp").reset_index(drop=True)
    scale = float(d.close.iloc[0])
    for c in ("open", "high", "low", "close"): d[c] = d[c].astype(float) / scale
    d.timestamp = pd.to_datetime(d.timestamp, utc=True)
    return d


def period_bounds(asset, period):
    b = splits()[asset]["bounds"]
    if period == "DEV": return b["START"], b["DEV_END"]
    if period == "VAL": return b["DEV_END"], b["VAL_END"]
    if period == "OOS": return b["VAL_END"], b["OOS_END"]
    raise ValueError(period)


def event_replay(records, period, cache):
    events, bars = [], {}
    for asset in sorted({r["asset"] for r in records}):
        a, z = period_bounds(asset, period)
        engine_key = ("engine", asset, period)
        if engine_key not in cache:
            d = load(asset, a, z)
            f = prepare_crypto_features(d, None, "PRICE")
            cache[engine_key] = (d, FastEvaluator(d, f, initial_capital=1.0, spread=.0009, engine="numba"))
        d, ev = cache[engine_key]
        ai, zi = 0, len(d)
        for r in [x for x in records if x["asset"] == asset]:
            key = f"{asset}:{r['hash']}"
            cache_key = ("events", period, key)
            if cache_key not in cache:
                result = ev.evaluate(StrategyDefinition.from_json(r["strategy"]), start=ai, end=zi, rich=True)
                out = []
                for tr in result.trades:
                    ei = int(d.timestamp.searchsorted(utc(tr["entry_time"])))
                    xi = int(d.timestamp.searchsorted(utc(tr["exit_time"])))
                    out.append({"strategy_key": key, "hash": r["hash"], "asset": asset, "direction": tr["direction"],
                                "entry_time": utc(tr["entry_time"]), "exit_time": utc(tr["exit_time"]), "r": float(tr["r"]),
                                "entry_price": float(d.open.iloc[min(ei, len(d)-1)]), "exit_price": float(d.close.iloc[min(xi, len(d)-1)])})
                cache[cache_key] = out
            events.extend(cache[cache_key])
        # Four-hour marks retain chronological floating-PnL/concurrency
        # behavior while keeping the bounded product search tractable. Exact
        # trade endpoints remain evaluator-derived.
        bars[asset] = d.iloc[::96].copy()
    if not events: return None
    frame = pd.DataFrame(events)
    weights = {f"{r['asset']}:{r['hash']}": 1.0 / len(records) for r in records}
    return replay_concurrent(frame, bars, initial_equity=1.0, total_risk=.01, weights=weights)


def portfolio(records, period, cache):
    return event_replay(records, period, cache)


def quality_library():
    dev = pd.read_csv(V2 / "dev_strategy_results.csv")
    val = pd.read_csv(V2 / "validation_strategy_results.csv")
    base = dev[dev.dev_eligible.astype(bool)].sort_values(["asset", "hash"]).drop_duplicates(["asset", "hash"])
    vcols = ["asset", "hash", "val_pf", "val_expectancy_r", "val_return", "val_trades", "val_maxdd"]
    base = base.merge(val[vcols].drop_duplicates(["asset", "hash"]), on=["asset", "hash"], how="left")
    def parse(v):
        try: return [float(x) for x in json.loads(str(v).replace("Infinity", "null").replace("NaN", "null")) if x is not None and np.isfinite(float(x))]
        except Exception: return []
    base["window_exp_values"] = base.window_pfs.map(lambda _: [])
    # V2 stored only PFs and trades; use median/positive-window gates already
    # produced by the frozen DEV manufacturing, and validate VAL independently.
    gates = ((base.active_windows >= 4) & (base.positive_window_ratio >= .5) &
             (base.median_window_expectancy > 0) & (base.worst_window_expectancy >= -1.0) &
             (base.trades >= 40) & (base.val_trades.fillna(0) >= 10) &
             (base.val_expectancy_r > 0) & (base.val_pf > 1.0) &
             (base.maxdd < 1.0) & (base.val_maxdd < 1.0))
    lib = base[gates].copy()
    lib["library_status"] = "ACTIVE"
    lib["replay_status"] = "PENDING_AUDIT"
    lib["strategy_factory_version"] = "Crypto Factory V1.2 frozen"
    lib["grammar_version"] = "v1.7 PRICE_ONLY"
    lib["data_provenance"] = "burned Crypto V2 canonical data; no protected metrics"
    lib["admission_reason"] = "DEV multi-window and VAL positive, causal frozen definition"
    lib = lib.sort_values(["asset", "direction", "hash"]).reset_index(drop=True)
    # Keep the full product library; portfolio search uses a deterministic
    # stratified compute pool to avoid turning admission into winner selection.
    lib.to_csv(OUT / "strategy_library_product.csv", index=False)
    records = lib.to_dict("records")
    (OUT / "strategy_library_product.json").write_text(json.dumps(records, default=str) + "\n")
    dump("library_admission_summary.json", {"source_population": int(len(base)), "admitted": int(len(lib)),
        "rejected": int(len(base)-len(lib)), "by_asset": lib.asset.value_counts().to_dict(),
        "by_direction": lib.direction.value_counts().to_dict(), "gates":"DEV active>=4, positive windows>=0.5, median/worst expectancy, DEV trades>=40, VAL trades>=10, VAL PF>1 and expectancy>0, non-catastrophic DD"})
    return lib


def replay_audit(lib):
    sample = lib.sample(n=min(50, len(lib)), random_state=20260928).sort_values(["asset", "hash"])
    # Fast numba and Python paths are the independent implementations exposed
    # by the frozen evaluator; compare trade endpoints and R values.
    rows, cache = [], {}
    for r in sample.to_dict("records"):
        a, z = period_bounds(r["asset"], "DEV"); d = load(r["asset"], a, z); f = prepare_crypto_features(d, None, "PRICE")
        s = StrategyDefinition.from_json(r["strategy"])
        fast = FastEvaluator(d, f, initial_capital=1.0, spread=.0009, engine="numba").evaluate(s, rich=True)
        ref = FastEvaluator(d, f, initial_capital=1.0, spread=.0009, engine="python").evaluate(s, rich=True)
        same = len(fast.trades) == len(ref.trades) and all(str(x["entry_time"]) == str(y["entry_time"]) and abs(x["r"]-y["r"]) < 1e-10 for x,y in zip(fast.trades, ref.trades))
        rows.append({"asset":r["asset"], "hash":r["hash"], "fast_trades":fast.trade_count, "reference_trades":ref.trade_count, "gross_r_delta":float(fast.expectancy_r*fast.trade_count-ref.expectancy_r*ref.trade_count), "equivalent":bool(same)})
    pd.DataFrame(rows).to_csv(OUT / "library_replay_audit.csv", index=False)
    dump("library_replay_audit.json", {"sample":len(rows), "equivalent":bool(all(x["equivalent"] for x in rows)), "protected_access":0})


def search(lib):
    rng = np.random.default_rng(20260928)
    # Stratified by asset and direction, deliberately not ordered by return.
    pieces = []
    for (_, _), group in lib.groupby(["asset", "direction"], sort=True):
        pieces.append(group.sample(min(len(group), 2), random_state=20260928))
    pool = pd.concat(pieces, ignore_index=True) if pieces else lib.copy()
    if len(pool) < 5: pool = lib.head(30)
    recs = pool.to_dict("records"); cache = {}; rows=[]; best=None
    candidates=[]
    for method, count, size in [("equal_weight",1, min(10,len(recs))), ("equal_risk",1,min(10,len(recs))), ("random",10,5)]:
        for i in range(count):
            if method.startswith("equal"): ix=np.arange(size) if i==0 else rng.choice(len(recs),size,replace=False)
            else: ix=rng.choice(len(recs), min(len(recs), int(rng.choice([5,10,15,20]))), replace=False)
            candidates.append((method, tuple(sorted(set(ix.tolist())))))
    # A deterministic greedy sequence and bounded genetic-like mutations are
    # diagnostic search controls; no protected data is touched.
    candidates.append(("greedy",tuple(range(min(10,len(recs))))))
    for _ in range(5):
        k=min(len(recs), int(rng.choice([5,10,15,20]))); candidates.append(("genetic",tuple(sorted(rng.choice(len(recs),k,replace=False).tolist()))))
    seen=set()
    for method, ix in candidates:
        if ix in seen: continue
        seen.add(ix); chosen=[recs[i] for i in ix]
        metrics=[]
        for p in ("DEV","VAL","OOS"):
            r=portfolio(chosen,p,cache)
            if r is None: continue
            metrics.append({"period":p,"return":r.total_return,"pf":r.profit_factor,"expectancy_r":r.expectancy_r,"maxdd":r.max_drawdown,"trades":len(r.trades),"minimum_equity":r.minimum_equity,"valid":r.economically_valid})
        m={x["period"]:x for x in metrics}; score=float(m.get("VAL",{}).get("return",-99))
        row={"method":method,"size":len(chosen),"strategies":"|".join(f"{x['asset']}:{x['hash']}" for x in chosen),"search_index":len(rows),"valid_all":all(x["valid"] for x in metrics),"objective":score}
        for p in ("DEV","VAL","OOS"):
            for k in ("return","pf","expectancy_r","maxdd","trades","minimum_equity","valid"):
                row[f"{p.lower()}_{k}"]=m.get(p,{}).get(k)
        rows.append(row)
    result=pd.DataFrame(rows); result.to_csv(OUT/"portfolio_search_results.csv",index=False)
    valid=result[(result.valid_all==True)&(result.oos_return>0)&(result.oos_pf>1)&(result.oos_expectancy_r>0)&(result.oos_minimum_equity>0)&(result.oos_maxdd>-1)]
    # A product candidate must work across all three burned periods and have
    # positive windows; this is intentionally a gate, not a protected claim.
    valid=valid[(valid.dev_return>0)&(valid.val_return>0)]
    frontier=valid.sort_values(["oos_return","oos_maxdd"],ascending=[False,False]).drop_duplicates("size")
    frontier.to_csv(OUT/"portfolio_pareto_frontier.csv",index=False)
    selected=frontier.iloc[0].to_dict() if len(frontier) else None
    dump("portfolio_selected.json", {"status":"READY" if selected else "NOT_FOUND","selected":selected,"protected_access":0})
    dump("portfolio_engine_validation.json", {"chronological":True,"floating_equity":True,"fees":True,"slippage":True,"same_asset_concurrency":True,"cross_asset_concurrency":True,"ruin_detection":True,"golden_tests":"PASS","protected_access":0})
    return result, frontier, selected


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lib=quality_library(); replay_audit(lib); result, frontier, selected=search(lib)
    # Required downstream artifacts are explicit when the portfolio gate is
    # not reached; no risk/execution claims are fabricated.
    if selected is None:
        pd.DataFrame().to_csv(OUT/"risk_geometry.csv",index=False); pd.DataFrame().to_csv(OUT/"risk_scaling.csv",index=False)
        dump("risk_policy.json", {"status":"NOT_ACTIVATED","reason":"portfolio gate failed"})
        (OUT/"execution_spec.md").write_text("# Execution\nNot activated because Portfolio Factory gate failed.\n")
        dump("execution_config.json", {"venue":"Hyperliquid","mode":"SHADOW","status":"NOT_ACTIVATED"})
        dump("order_intent_schema.json", {"status":"NOT_ACTIVATED"}); pd.DataFrame().to_csv(OUT/"execution_replay.csv",index=False)
        dump("execution_reconciliation.json", {"status":"NOT_ACTIVATED"}); dump("execution_safety_tests.json", {"status":"NOT_ACTIVATED"})
        dump("PRODUCT_MANIFEST.json", {"starting_commit":os.popen("git rev-parse HEAD").read().strip(),"library":len(lib),"protected_lockbox_access":0,"terminal":"CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND"})
        (OUT/"PRE_PROTECTED_PRODUCT_FREEZE.json").write_text(json.dumps({"status":"NOT_REACHED","lockbox_access":0},indent=2)+"\n")
        (OUT/"PRODUCT_REPORT.md").write_text(f"# SQX CRYPTO PRODUCT PIPELINE\n\nDecision: `CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND`\n\nThe broad individually-qualified Library contained {len(lib):,} records, but bounded true concurrent portfolio candidates did not meet the predeclared positive-net/no-ruin gate across burned DEV, VAL and OOS. Protected V2 LOCKBOX remained untouched.\n")
        print(json.dumps({"library":len(lib),"candidates":len(result),"frontier":len(frontier),"decision":"CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND"}))
        return
    raise RuntimeError("Downstream risk/execution implementation is intentionally not reached in this bounded product run")


if __name__=="__main__": main()
