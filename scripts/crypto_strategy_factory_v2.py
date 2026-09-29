#!/usr/bin/env python3
"""Crypto Strategy Factory V2: persistence diagnostics and DEV-only manufacturing.

This experiment is intentionally separate from the closed V1/V2 reports.  The
only labels taken from OOS are burned research labels; all factory predictors
and all manufacturing fitness are DEV/VAL-free of OOS.
"""
from __future__ import annotations

import argparse, hashlib, json, math, os, platform, subprocess, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/reports/crypto_economic_strategy_contract_v1"
FACT = ROOT / "runs/reports/crypto_factory_v2"
OUT = ROOT / "runs/reports/crypto_strategy_factory_v2"
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from crypto_economic_strategy_contract_v1 import prepare_period, bounded_replay, RISK_FRACTION
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition
from sqx_engine.crypto.generator import CryptoRandomGenerator, CryptoGeneticGenerator

ASSETS = ("ADA", "AVAX", "BNB", "BTC", "DOGE", "ETH", "LINK", "SOL", "TRX")

def sha(path):
    h = hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def dump(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + "\n")

def git_commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

def read_inputs():
    admission = pd.read_csv(BASE / "library_v2_admission_reasons.csv")
    oos = pd.read_csv(BASE / "admitted_vs_rejected_OOS.csv")
    if len(admission) != 7017 or admission.hash.nunique() != 7017:
        raise RuntimeError("frozen candidate universe is not 7,017 unique definitions")
    oos["oos_ruin"] = oos["oos_ruin"].map(lambda x: str(x).strip().lower() in {"true", "1", "yes"})
    a = admission.merge(oos[["hash", "oos_pf", "oos_expectancy_r", "oos_economic_expectancy", "oos_return", "oos_maxdd", "oos_ruin"]], on="hash", how="left")
    # Preserve the prior burned diagnostic label exactly: positive OOS PF.
    # Ruin remains a separate diagnostic dimension and is never hidden.
    a["oos_survivor"] = a.oos_pf > 1.0
    if int((a.admitted & a.oos_survivor).sum()) != 82:
        raise RuntimeError("frozen 82-survivor baseline did not reproduce")
    return a

def strategy_complexity(s):
    try:
        x = json.loads(s) if isinstance(s, str) else s
        entry = x.get("entry", x.get("entry_predicates", [])); exit_ = x.get("exit", x.get("exit_predicates", []))
        return {"predicate_count": len(entry) + len(exit_), "entry_count": len(entry), "exit_count": len(exit_),
                "json_length": len(json.dumps(x, sort_keys=True)), "has_stop": int(bool(x.get("stop_loss", x.get("stop", None)))),
                "has_target": int(bool(x.get("take_profit", x.get("target", None))))}
    except Exception:
        return {"predicate_count": np.nan, "entry_count": np.nan, "exit_count": np.nan, "json_length": np.nan, "has_stop": np.nan, "has_target": np.nan}

def extract_window_events(d, definition, features, start, end):
    result = FastEvaluator(d, features, initial_capital=1.0, spread=.0009, engine="numba").evaluate(definition, start=start, end=end, rich=True)
    out = []
    for tr in result.trades:
        et, xt = pd.Timestamp(tr["entry_time"]), pd.Timestamp(tr["exit_time"])
        ei = min(max(int(d.timestamp.searchsorted(et)), 0), len(d)-1)
        xi = min(max(int(d.timestamp.searchsorted(xt)), 0), len(d)-1)
        out.append({"entry_time": et, "exit_time": xt, "direction": tr["direction"], "r": float(tr["r"]),
                    "entry_price": float(d.open.iloc[ei]), "exit_price": float(d.close.iloc[xi]),
                    "entry_index": ei, "exit_index": xi, "asset": str(definition.market)})
    return out

def exact_windows(admitted):
    windows = pd.read_csv(FACT / "dev_internal_windows.csv", parse_dates=["start", "end"])
    rows = []
    cache_dir = OUT / "_window_cache"; cache_dir.mkdir(parents=True, exist_ok=True)
    for asset, group in admitted.groupby("asset", sort=True):
        cached = cache_dir / f"{asset}.csv"
        if cached.exists():
            rows.extend(pd.read_csv(cached, parse_dates=["start", "end"]).to_dict("records")); print(f"loaded exact DEV windows: {asset}", flush=True); continue
        d, f = prepare_period(asset, "DEV"); bars = {asset: d[["timestamp", "close"]].copy()}
        for rec in group.to_dict("records"):
            definition = StrategyDefinition.from_json(rec["strategy"])
            for w in windows[windows.asset == asset].itertuples(index=False):
                st = int(d.timestamp.searchsorted(pd.Timestamp(w.start))); en = int(d.timestamp.searchsorted(pd.Timestamp(w.end)))
                ev = extract_window_events(d, definition, f, st, en)
                z = bounded_replay(ev, bars)
                rows.append({"hash": rec["hash"], "strategy_id": rec["strategy_id"], "asset": asset,
                             "direction": rec["direction"], "window": w.window, "start": w.start, "end": w.end, **z})
        pd.DataFrame([r for r in rows if r["asset"] == asset]).to_csv(cached, index=False)
        print(f"exact DEV windows: {asset} ({len(group)} strategies)", flush=True)
    return pd.DataFrame(rows)

def add_window_features(base, wm):
    out = base.copy(); g = wm.groupby("hash", sort=False)
    metrics = ["return", "economic_expectancy", "expectancy_r", "pf", "trades", "maxdd", "minimum_equity", "realized_pnl"]
    for metric in metrics:
        piv = wm.pivot(index="hash", columns="window", values=metric)
        piv.columns = [f"window_{metric}_{c}" for c in piv.columns]
        out = out.merge(piv, left_on="hash", right_index=True, how="left")
    def feats(x):
        x = x.sort_values("window"); positive = x.economic_expectancy > 0; returns = x["return"].to_numpy(float); ex = x.economic_expectancy.to_numpy(float)
        pnl = x.realized_pnl.to_numpy(float); pos_pnl = np.maximum(pnl, 0); total_pos = pos_pnl.sum()
        share = float(pos_pnl.max() / total_pos) if total_pos > 0 else 0.0
        top2 = float(np.sort(pos_pnl)[-2:].sum() / total_pos) if total_pos > 0 else 0.0
        active = x.trades >= 3
        return pd.Series({"dev_positive_windows": int(positive.sum()), "dev_positive_window_fraction": float(positive.mean()),
                          "dev_negative_streak": max_streak(~positive.to_numpy()), "dev_worst_window_expectancy": float(np.min(ex)),
                          "dev_median_window_expectancy": float(np.median(ex)), "dev_window_expectancy_std": float(np.std(ex)),
                          "dev_worst_window_return": float(np.min(returns)), "dev_median_window_return": float(np.median(returns)),
                          "dev_best_window_share": share, "dev_top2_window_share": top2,
                          "dev_active_windows": int(active.sum()), "dev_min_window_trades": int(x.trades.min()),
                          "dev_trade_dispersion": float(x.trades.std(ddof=0) / max(x.trades.mean(), 1e-12)),
                          "dev_late_expectancy": float(ex[-1]), "dev_early_expectancy": float(ex[0]),
                          "dev_expectancy_slope": slope(ex), "dev_return_slope": slope(returns)})
    f = wm.groupby("hash", sort=False).apply(feats, include_groups=False)
    out = out.merge(f, left_on="hash", right_index=True, how="left")
    return out

def max_streak(values):
    best = cur = 0
    for v in values:
        cur = cur + 1 if bool(v) else 0; best = max(best, cur)
    return best

def slope(v):
    v = np.asarray(v, float)
    return float(np.polyfit(np.arange(len(v)), v, 1)[0]) if len(v) >= 2 and np.isfinite(v).all() else np.nan

def effect(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float); a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2) if len(a) > 1 and len(b) > 1 else np.nan
    return float((np.median(a)-np.median(b)) / pooled) if pooled and np.isfinite(pooled) else np.nan

def quality_table(a):
    rows=[]
    for metric in ["dev_pf","dev_economic_expectancy","dev_return","dev_trades","val_pf","val_economic_expectancy","val_return","val_trades","dev_maxdd","val_maxdd","dev_minimum_equity","val_minimum_equity"]:
        s=a[a.oos_survivor][metric]; f=a[~a.oos_survivor][metric]
        rows.append({"feature":metric,"survivor_median":s.median(),"failure_median":f.median(),"median_difference":s.median()-f.median(),"standardized_effect":effect(s,f)})
    return pd.DataFrame(rows)

def policy_rows(a):
    base = a.admitted.astype(bool)
    rules = {
        "BASELINE": base,
        "PERSISTENCE": base & (a.dev_positive_window_fraction >= .50) & (a.dev_active_windows >= 4),
        "LOW_CONCENTRATION": base & (a.dev_best_window_share <= .70) & (a.dev_top2_window_share <= .95),
        "RECENT_EDGE": base & (a.dev_late_expectancy > 0) & (a.val_economic_expectancy > 0),
        "ROBUST_COMBINED": base & (a.dev_positive_window_fraction >= .50) & (a.dev_active_windows >= 4) & (a.dev_best_window_share <= .70) & (a.dev_late_expectancy > 0) & (a.val_economic_expectancy > 0),
    }
    rows=[]
    for name, mask in rules.items():
        g=a[mask]; rows.append({"policy":name,"selected":len(g),"oos_positive_rate":float(g.oos_survivor.mean()) if len(g) else 0.,"median_oos_pf":g.oos_pf.median() if len(g) else np.nan,"median_oos_expectancy":g.oos_economic_expectancy.median() if len(g) else np.nan,"median_oos_return":g.oos_return.median() if len(g) else np.nan,"oos_ruin_rate":g.oos_ruin.mean() if len(g) else 0.,"research_only":True})
    return pd.DataFrame(rows)

def diagnostics():
    OUT.mkdir(parents=True, exist_ok=True); a=read_inputs(); admitted=a[a.admitted].copy(); wm=exact_windows(admitted); wm.to_parquet(OUT/"dev_window_metrics.parquet", index=False)
    feat=add_window_features(admitted, wm)
    for c in ["dev_pf","dev_economic_expectancy","dev_return","dev_trades","dev_maxdd","dev_minimum_equity","val_pf","val_economic_expectancy","val_return","val_trades","val_maxdd","val_minimum_equity"]:
        if c not in feat: feat[c]=np.nan
    feat["val_dev_pf_ratio"] = feat.val_pf / feat.dev_pf.replace(0,np.nan); feat["val_dev_expectancy_change"] = feat.val_economic_expectancy-feat.dev_economic_expectancy; feat["val_dev_return_change"] = feat.val_return-feat.dev_return; feat["val_dev_trade_rate_ratio"] = feat.val_trades/feat.dev_trades.replace(0,np.nan)
    complexities=feat.strategy.map(strategy_complexity).apply(pd.Series); feat=pd.concat([feat.drop(columns=["strategy"],errors="ignore"),complexities],axis=1)
    feat.to_csv(OUT/"persistence_features.csv", index=False); a.merge(feat.drop(columns=[c for c in a.columns if c in feat.columns and c != "hash"], errors="ignore"), on="hash", how="left", suffixes=("", "_feature")).to_csv(OUT/"survivor_failure_dataset.csv",index=False)
    quality_table(feat.assign(oos_survivor=feat.hash.map(a.set_index("hash").oos_survivor))).to_csv(OUT/"basic_quality_analysis.csv",index=False)
    stab=feat[["hash","dev_pf","val_pf","val_dev_pf_ratio","dev_economic_expectancy","val_economic_expectancy","val_dev_expectancy_change","dev_return","val_return","val_dev_return_change","dev_trades","val_trades","val_dev_trade_rate_ratio","oos_survivor"]]; stab.to_csv(OUT/"dev_val_stability.csv",index=False)
    wm.to_csv(OUT/"dev_window_metrics.csv",index=False); feat[["hash","dev_best_window_share","dev_top2_window_share","dev_positive_window_fraction"]].to_csv(OUT/"profit_concentration.csv",index=False); feat[["hash","dev_trades","val_trades","dev_min_window_trades","dev_active_windows","val_dev_trade_rate_ratio"]].to_csv(OUT/"trade_support.csv",index=False); feat[["hash","dev_early_expectancy","dev_late_expectancy","val_economic_expectancy"]].to_csv(OUT/"edge_recency.csv",index=False)
    feat[["hash","dev_maxdd","val_maxdd","dev_minimum_equity","val_minimum_equity","dev_trades","val_trades"]].to_csv(OUT/"loss_geometry.csv",index=False)
    pd.DataFrame([{"scope":"DEV-only diagnostic","regime_features":"return/realized-volatility partitions deferred to raw-market feature audit","status":"descriptive scaffold; no regime rule created"}]).to_csv(OUT/"regime_robustness.csv",index=False)
    # Burned label is only attached after the DEV/VAL features are frozen in this diagnostic artifact.
    p=policy_rows(feat); p.to_csv(OUT/"persistence_policy_comparison.csv",index=False)
    sens=[]
    for t in (.4,.5,.6,.7):
        g=feat[feat.dev_positive_window_fraction>=t]; g=g[g.oos_survivor==g.oos_survivor] # labels are diagnostic only
        sens.append({"rule":"positive_window_fraction","threshold":t,"selected":len(g),"oos_positive_rate":g.oos_survivor.mean() if len(g) else np.nan,"research_only":True})
    pd.DataFrame(sens).to_csv(OUT/"threshold_sensitivity.csv",index=False)
    allc=a.copy(); allc["group"]=np.where(allc.admitted,"ADMITTED","REJECTED"); allc.to_csv(OUT/"survivor_failure_dataset.csv",index=False)
    # Direction attrition is a frozen descriptive audit, not a new rule.
    d=a.groupby("direction").agg(candidates=("hash","size"),admitted=("admitted","sum"),oos_survivors=("oos_survivor","sum")).reset_index(); d.to_csv(OUT/"direction_attrition.csv",index=False)
    dump("short_pipeline_audit.json",{"source_universe":a[a.direction=="SHORT"].shape[0],"hard_valid":int(((a.direction=="SHORT") & (~a.dev_ruin) & (~a.val_ruin)).sum()),"dev_valid":int(((a.direction=="SHORT") & (a.dev_pf>1) & (a.dev_economic_expectancy>0) & (a.dev_return>0) & (a.dev_trades>=30) & (~a.dev_ruin)).sum()),"val_valid":int(((a.direction=="SHORT") & (a.val_pf>1) & (a.val_economic_expectancy>0) & (a.val_return>0) & (a.val_trades>=10) & (~a.val_ruin)).sum()),"admitted":int(((a.direction=="SHORT") & a.admitted).sum()),"finding":"economic attrition in frozen candidate records; no asymmetry fix applied"})
    quality_table(feat.assign(oos_survivor=feat.oos_survivor)).to_csv(OUT/"survival_signal_analysis.csv",index=False)
    dump("survivor_failure_summary.json",{"candidate_count":len(a),"admitted":int(a.admitted.sum()),"survivors":int((a.admitted&a.oos_survivor).sum()),"failures":int((a.admitted&~a.oos_survivor).sum()),"oos_used_as_label_only":True,"lockbox_access":0})
    dump("survival_signal_summary.json",{"method":"descriptive DEV/VAL-only feature effects; OOS label used after feature construction","top_features":quality_table(feat.assign(oos_survivor=feat.hash.map(a.set_index("hash").oos_survivor))).sort_values("standardized_effect",key=lambda x:x.abs(),ascending=False).head(8).to_dict("records")})
    (OUT/"BURNED_OOS_RESEARCH_NOTICE.md").write_text("# Burned OOS research notice\n\nOOS metrics and survivor labels in this directory are historical research labels only. They were not used in manufacturing fitness, admission thresholds, or candidate generation. LOCKBOX remains untouched.\n")
    return feat

def write_specs():
    OUT.mkdir(parents=True,exist_ok=True)
    manifest={"experiment":"crypto_strategy_factory_v2","starting_commit":"bf2c9c1","economic_contract":str(BASE/"STRATEGY_ECONOMIC_CONTRACT.md"),"candidate_universe":7017,"old_library_v2":374,"grammar":"v1.7 PRICE_ONLY","segments":{"manufacturing":"DEV only","admission":"DEV+VAL","OOS":"burned research label only","LOCKBOX":"untouched"},"lockbox_access":0}
    dump("FACTORY_V2_BASELINE_MANIFEST.json",manifest); dump("EXPERIMENT_MANIFEST.json",manifest)
    (OUT/"STRATEGY_FACTORY_V2_SPEC.md").write_text("# Strategy Factory V2\n\nFactory V2 retains the v1.7 PRICE_ONLY grammar and frozen bounded economic contract. Manufacturing uses DEV-only causal internal windows; VAL is a single post-manufacturing admission gate. OOS is never used in fitness or admission.\n\nThe factory objective is temporal persistence: positive exact economics across multiple DEV windows, adequate support, limited profit concentration, and a live late-DEV/VAL edge.\n")
    (OUT/"PERSISTENCE_FITNESS_SPEC.md").write_text("# Persistence fitness\n\nFrozen before manufacturing: invalid/ruined candidates are rejected; among valid DEV candidates prefer positive economic expectancy, at least four active windows, positive-window fraction, median/worst-window expectancy, trade support, low best-window concentration, and a live late-DEV edge. No VAL or OOS statistic enters manufacturing fitness.\n")

def candidate_score(z, window_rows):
    ex = np.array([r["economic_expectancy"] for r in window_rows], float)
    active = np.array([r["trades"] >= 3 for r in window_rows])
    exa = ex[active] if active.any() else np.array([-1.0])
    positive = float(np.mean(exa > 0))
    pnl = np.maximum(np.array([r["realized_pnl"] for r in window_rows], float), 0)
    concentration = float(pnl.max() / pnl.sum()) if pnl.sum() > 0 else 1.0
    # Small transparent DEV-only score.  Invalidity is hard, persistence is
    # rewarded, and extreme aggregate PF is deliberately absent.
    if z["ruin"] or z["trades"] < 20 or z["economic_expectancy"] <= 0:
        return -1e9
    return float(z["economic_expectancy"] + .002 * positive + .0001 * min(z["trades"], 500) - .002 * concentration + .001 * max(0, exa[-1]))

def manufacture():
    """Bounded exact smoke/manufacturing run; budgets are explicit in output."""
    random_budget = int(os.getenv("SQX_V2_RANDOM_BUDGET", "20")); genetic_budget = int(os.getenv("SQX_V2_GENETIC_BUDGET", "40"))
    rows=[]; started=time.time()
    for ai, asset in enumerate(ASSETS):
        d, f = prepare_period(asset, "DEV"); bars={asset:d[["timestamp","close"]].copy()}; ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine="numba")
        cuts=np.linspace(0, len(d), 5, dtype=int); windows=[(int(cuts[i]), int(cuts[i+1])) for i in range(4)]
        rg=CryptoRandomGenerator(asset,"M15",seed=9100+ai,min_predicates=1,max_predicates=2,grammar_version="v1.7",information_variant="PRICE")
        gg=CryptoGeneticGenerator(asset,"M15",seed=8100+ai,min_predicates=1,max_predicates=2,grammar_version="v1.7",information_variant="PRICE",population_size=40,mode="scale")
        seen=set()
        def one(s, kind):
            if s.canonical_hash in seen: return None
            seen.add(s.canonical_hash); full=ev.evaluate(s,start=0,end=len(d),rich=True)
            events=extract_window_events(d,s,f,0,len(d)); z=bounded_replay(events,bars); wr=[]
            for st,en in windows:
                we=extract_window_events(d,s,f,st,en); wr.append(bounded_replay(we,bars))
            return {"asset":asset,"timeframe":"M15","kind":kind,"strategy_id":s.readable_id,"hash":s.canonical_hash,"strategy":s.to_json(),"direction":s.direction,"trades":z["trades"],"pf":z["pf"],"economic_expectancy":z["economic_expectancy"],"return":z["return"],"maxdd":z["maxdd"],"minimum_equity":z["minimum_equity"],"ruin":z["ruin"],"positive_window_fraction":float(np.mean([x["economic_expectancy"]>0 for x in wr])),"active_windows":int(sum(x["trades"]>=3 for x in wr)),"best_window_share":float(max([max(x["realized_pnl"],0) for x in wr],default=0)/max(sum(max(x["realized_pnl"],0) for x in wr),1e-12)),"fitness":candidate_score(z,wr)}
        for i in range(random_budget):
            x=one(rg.ask(),"RANDOM");
            if x: rows.append(x)
        for i in range(genetic_budget):
            s=gg.ask(known_hashes=seen); x=one(s,"GENETIC")
            if x: rows.append(x)
            if x:
                class R: pass
                rr=R(); rr.expectancy_r=x["economic_expectancy"]; rr.sharpe=0.; rr.max_drawdown=-x["maxdd"]; gg.tell(s,rr)
        print(f"manufactured {asset}: {len([x for x in rows if x['asset']==asset])}",flush=True)
    r=pd.DataFrame(rows); r.to_parquet(OUT/"factory_v2_random_results.parquet",index=False); r.to_parquet(OUT/"factory_v2_genetic_results.parquet",index=False)
    r.to_csv(OUT/"random_vs_genetic.csv",index=False)
    dump("manufacturing_summary.json",{"random_requested_per_asset":random_budget,"genetic_requested_per_asset":genetic_budget,"random_evaluations":int((r.kind=="RANDOM").sum()),"genetic_evaluations":int((r.kind=="GENETIC").sum()),"unique":int(r.hash.nunique()),"economic_evaluator":"bounded exact replay","segments":"DEV only","elapsed_seconds":time.time()-started})
    # This is the mandatory freeze before any VAL access.
    freeze={"status":"PRE_VAL_FACTORY_FREEZE","commit":git_commit(),"grammar":"v1.7 PRICE_ONLY","economic_contract_hash":sha(BASE/"STRATEGY_ECONOMIC_CONTRACT.md"),"fitness_hash":sha(OUT/"PERSISTENCE_FITNESS_SPEC.md"),"manufactured_hash":sha(OUT/"random_vs_genetic.csv"),"val_accessed":False,"oos_accessed":False,"lockbox_access":0}
    (OUT/"PRE_VAL_FACTORY_FREEZE.json").write_text(json.dumps(freeze,indent=2)+"\n")
    return r

def val_and_oos():
    freeze=json.loads((OUT/"PRE_VAL_FACTORY_FREEZE.json").read_text())
    if freeze.get("status")!="PRE_VAL_FACTORY_FREEZE": raise RuntimeError("VAL requires frozen Factory V2")
    r=pd.read_csv(OUT/"random_vs_genetic.csv") if (OUT/"random_vs_genetic.csv").exists() else pd.read_parquet(OUT/"factory_v2_random_results.parquet")
    vals=[]
    for asset,g in r.groupby("asset"):
        d,f=prepare_period(asset,"VAL"); ev=FastEvaluator(d,f,initial_capital=1.,spread=.0009,engine="numba")
        for rec in g.to_dict("records"):
            x=ev.evaluate(StrategyDefinition.from_json(rec["strategy"]),start=0,end=len(d),rich=True); events=extract_window_events(d,StrategyDefinition.from_json(rec["strategy"]),f,0,len(d)); z=bounded_replay(events,{asset:d[["timestamp","close"]].copy()})
            vals.append({**rec,"val_trades":z["trades"],"val_pf":z["pf"],"val_expectancy":z["economic_expectancy"],"val_return":z["return"],"val_ruin":z["ruin"]})
    v=pd.DataFrame(vals); v.to_parquet(OUT/"library_v3_manufactured_val.parquet",index=False)
    good=v[(v.trades>=20)&(v.val_trades>=10)&(v.economic_expectancy>0)&(v.val_expectancy>0)&(v.val_pf>1)&(~v.ruin)&(~v.val_ruin)&(v.positive_window_fraction>=.5)&(v.active_windows>=4)].copy()
    good=good.drop_duplicates("hash").sort_values(["fitness","hash"],ascending=[False,True]); good.to_csv(OUT/"library_v3_candidate.csv",index=False); good.to_csv(OUT/"library_v3_admission_reasons.csv",index=False)
    dump("library_v3_summary.json",{"manufactured":len(v),"val_evaluated":len(v),"admitted":len(good),"oos_used_for_admission":False,"lockbox_access":0})
    return good

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--phase",choices=["diagnostics","spec","manufacture","val"],default="diagnostics"); args=ap.parse_args()
    if args.phase=="spec": write_specs(); print("spec written"); return
    write_specs()
    if args.phase=="diagnostics": diagnostics(); print(json.dumps({"status":"diagnostics_complete","lockbox_access":0}))
    elif args.phase=="manufacture": manufacture(); print(json.dumps({"status":"pre_val_frozen","lockbox_access":0}))
    else: val_and_oos(); print(json.dumps({"status":"val_complete","lockbox_access":0}))

if __name__=="__main__": main()
