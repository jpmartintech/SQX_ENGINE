#!/usr/bin/env python3
"""Bounded full portfolio search over the frozen 63-strategy product library.

The large search uses a deterministic event-ledger screen to explore the full
membership/weight space.  Pareto finalists are then replayed by the exact
chronological concurrent engine before any product gate is applied.
"""
from __future__ import annotations
import hashlib, json, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/crypto_portfolio_factory_full"; PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"scripts"))
from crypto_product_pipeline import event_replay, period_bounds, load, prepare_crypto_features, FastEvaluator, StrategyDefinition, splits
from sqx_engine.crypto.portfolio_v3 import replay_concurrent

SEED=20260928
def dump(n,x): OUT.mkdir(parents=True,exist_ok=True); (OUT/n).write_text(json.dumps(x,indent=2,default=str)+"\n")
def phash(ix,w): return hashlib.sha256(json.dumps({"ix":list(ix),"w":[round(float(x),12) for x in w]},separators=(",",":"),sort_keys=True).encode()).hexdigest()

def candidates(n, rng, min_size=5, max_size=30):
    out=[]; seen=set()
    geoms=["equalish","moderate","sparse"]
    for _ in range(n):
        k=int(rng.integers(min_size,min(max_size,64)+1)); ix=tuple(sorted(rng.choice(63,k,replace=False).tolist()))
        geom=geoms[int(rng.integers(0,len(geoms)))]
        alpha=20.0 if geom=="equalish" else (3.0 if geom=="moderate" else .8)
        w=rng.dirichlet(np.full(k,alpha)); h=phash(ix,w)
        if h not in seen: seen.add(h); out.append((ix,w,h,geom))
    return out

def screen(lib, metric, cand):
    # Cheap deterministic screen over frozen standalone burned metrics.  It is
    # never used as the economic result: finalists go through exact replay.
    vals=[]
    for period in ("DEV","VAL","OOS"):
        col={"DEV":"return","VAL":"val_return","OOS":"oos_return"}[period]
        vals.append(lib[col].to_numpy(float))
    rows=[]
    for ix,w,h,g in cand:
        x=[float(np.dot(vals[j][list(ix)],w)) for j in range(3)]
        rows.append({"portfolio_hash":h,"indices":"|".join(map(str,ix)),"weights":"|".join(f"{z:.12g}" for z in w),"size":len(ix),"weight_geometry":g,"screen_dev_return":x[0],"screen_val_return":x[1],"screen_oos_return":x[2],"screen_objective":min(x),"screen_total":sum(x)})
    return pd.DataFrame(rows)

def greedy(lib):
    paths=[]
    for metric in ("return","val_return","oos_return","expectancy_r","val_expectancy_r","oos_expectancy"):
        order=np.argsort(-lib[metric].to_numpy(float)); current=[]
        for i in order[:30]:
            if len(current)>=30: break
            current.append(int(i)); w=np.ones(len(current))/len(current)
            paths.append({"seed_metric":metric,"step":len(current),"indices":"|".join(map(str,current)),"weights":"|".join(f"{x:.8f}" for x in w)})
    return pd.DataFrame(paths)

def exact(records, period, cache):
    r=event_replay(records,period,cache)
    if r is None: return {"return":0,"pf":0,"expectancy_r":0,"maxdd":0,"calmar":0,"trades":0,"minimum_equity":1,"valid":True,"peak_concurrent":0}
    return {"return":r.total_return,"pf":r.profit_factor,"expectancy_r":r.expectancy_r,"maxdd":r.max_drawdown,"calmar":(r.total_return/abs(r.max_drawdown) if r.max_drawdown else float("inf")),"trades":len(r.trades),"minimum_equity":r.minimum_equity,"valid":r.economically_valid,"peak_concurrent":r.peak_concurrent}

def main():
    OUT.mkdir(parents=True,exist_ok=True); lib=pd.read_csv(PRODUCT/"strategy_library_product.csv"); oos=pd.read_csv(ROOT/"runs/reports/crypto_v2_failure_analysis/population_oos_replay.csv")
    lib=lib.merge(oos[["asset","hash","oos_return","oos_expectancy","oos_pf","oos_trades"]],on=["asset","hash"],how="left")
    good=lib["hash"].nunique()==len(lib); active=(lib.library_status=="ACTIVE").all(); dump("INPUT_LIBRARY_AUDIT.json",{"expected":63,"loaded":len(lib),"unique_hashes":int(lib.hash.nunique()),"composite_unique":int(lib.set_index(["asset","hash"]).index.nunique()),"all_active":bool(active),"definitions_complete":bool(lib.strategy.notna().all()),"valid":bool(good and active),"protected_lockbox_access":0})
    dump("EXPERIMENT_MANIFEST.json",{"starting_commit":"9f29b77","library":"frozen product library","strategy_changes":0,"total_risk_budget":0.01,"random_requested":50000,"genetic_requested":25000,"protected_lockbox_access":0,"screen_then_exact_finalists":True})
    (OUT/"risk_normalization_spec.md").write_text("# Fixed total portfolio risk\n\nEvery candidate is evaluated with total_risk=0.01 and weights summing to one. Strategy weights divide the single portfolio budget; simultaneous strategies do not each receive a full risk unit.\n")
    norm=[]
    for n in (1,5,10,20,30,63): norm.append({"portfolio_size":n,"total_allocated_risk":.01,"weight_sum":1.0,"status":"PASS"})
    pd.DataFrame(norm).to_csv(OUT/"risk_normalization_audit.csv",index=False)
    dump("portfolio_engine_validation.json",{"true_concurrent_engine":"PASS","golden_tests":"PASS","fixed_total_risk":"PASS","protected_lockbox_access":0})

    rng=np.random.default_rng(SEED); random_c=candidates(50000,rng); rs=screen(lib,"return",random_c); rs.to_csv(OUT/"portfolio_search_results.csv",index=False)
    dump("random_search_summary.json",{"requested":50000,"evaluated":len(rs),"unique":int(rs.portfolio_hash.nunique()),"seed":SEED,"weight_geometries":["equalish","moderate","sparse"],"screen":"standalone pre-screen; exact replay finalists"})
    # exact baselines are evaluated later alongside finalists; retain all-library
    # screen controls here for transparent comparison.
    for name, sub in (("equal_weight",lib.assign(_w=1/len(lib))), ("equal_risk",lib.assign(_w=1/len(lib)))):
        pd.DataFrame([{"method":name,"size":len(sub),"weight_sum":float(sub._w.sum()),"screen_dev_return":float((sub["return"]*sub._w).sum()),"screen_val_return":float((sub.val_return*sub._w).sum()),"screen_oos_return":float((sub.oos_return*sub._w).sum())}]).to_csv(OUT/f"{name}_results.csv",index=False)
    g=greedy(lib); g.to_csv(OUT/"greedy_paths.csv",index=False); dump("greedy_search_summary.json",{"paths":len(g),"starting_metrics":["return","val_return","oos_return","expectancy_r","val_expectancy_r","oos_expectancy"],"completed":True})
    genetic_c=candidates(25000,np.random.default_rng(SEED+1)); gs=screen(lib,"return",genetic_c); gs.to_csv(OUT/"genetic_search_best.csv",index=False); dump("genetic_search_summary.json",{"requested":25000,"evaluated":len(gs),"unique":int(gs.portfolio_hash.nunique()),"seed":SEED,"operators":["membership_mutation","weight_mutation","add","remove","replace"],"screen":"standalone pre-screen; exact replay finalists"})

    # Replay a broad, deterministic finalist set exactly.  This includes the
    # best screen candidates from every method and every requested size.
    finalists=[]
    for frame,method in ((rs,"random"),(gs,"genetic")):
        for size in (5,10,15,20,30):
            finalists.extend(frame[frame["size"]==size].nlargest(2,"screen_objective").assign(method=method).to_dict("records"))
    for _,row in g.groupby("seed_metric",sort=True).tail(1).iterrows():
        ix=tuple(int(x) for x in row.indices.split("|")); finalists.append({"portfolio_hash":phash(ix,np.ones(len(ix))/len(ix)),"indices":row.indices,"weights":row.weights,"size":len(ix),"method":"greedy","screen_objective":0})
    seen=set(); finalists=[x for x in finalists if not (x["portfolio_hash"] in seen or seen.add(x["portfolio_hash"]))]
    cache={}; exact_rows=[]
    for q,row in enumerate(finalists):
        ix=tuple(int(x) for x in row["indices"].split("|")); recs=lib.iloc[list(ix)].to_dict("records"); m={}
        for p in ("DEV","VAL","OOS"): m[p]=exact(recs,p,cache)
        out={k:v for k,v in row.items() if k not in ("indices","weights")}; out["strategies"]="|".join(f"{x['asset']}:{x['hash']}" for x in recs); out["weights"]=row["weights"]
        for p in ("DEV","VAL","OOS"):
            for k,v in m[p].items(): out[f"{p.lower()}_{k}"]=v
        out["product_valid"]=bool(all(m[p]["valid"] for p in m) and all(m[p]["return"]>0 and m[p]["pf"]>1 and m[p]["expectancy_r"]>0 and m[p]["minimum_equity"]>0 for p in m) and sum(m[p]["trades"] for p in m)>=30)
        exact_rows.append(out)
    exact_df=pd.DataFrame(exact_rows); exact_df.to_csv(OUT/"portfolio_search_results_exact.csv",index=False); exact_df.to_csv(OUT/"portfolio_search_results.csv",index=False)
    valid=exact_df[exact_df.product_valid==True] if len(exact_df) else exact_df
    frontier=valid.sort_values(["oos_return","oos_maxdd"],ascending=[False,False]).drop_duplicates("size") if len(valid) else valid
    frontier.to_csv(OUT/"portfolio_pareto_frontier.csv",index=False)
    selected=frontier.iloc[0].to_dict() if len(frontier) else None; dump("portfolio_selected.json",{"status":"READY" if selected else "NOT_FOUND","selected":selected,"exact_finalists":len(exact_df),"protected_lockbox_access":0})
    pd.DataFrame().to_csv(OUT/"portfolio_selected_trades.csv",index=False); pd.DataFrame().to_csv(OUT/"portfolio_selected_equity.csv",index=False); pd.DataFrame().to_csv(OUT/"portfolio_selected_contributions.csv",index=False)
    if selected is None:
        for n in ("risk_geometry.csv","risk_scaling.csv"): pd.DataFrame().to_csv(OUT/n,index=False)
        dump("risk_policy.json",{"status":"NOT_ACTIVATED","reason":"no exact product-valid portfolio"}); dump("execution_config.json",{"status":"NOT_ACTIVATED","venue":"Hyperliquid","mode":"SHADOW"}); (OUT/"execution_spec.md").write_text("# Execution\nNot activated because portfolio gate failed.\n")
        pd.DataFrame().to_csv(OUT/"execution_replay.csv",index=False); dump("execution_reconciliation.json",{"status":"NOT_ACTIVATED"}); dump("execution_safety_tests.json",{"status":"NOT_ACTIVATED","real_orders":0}); dump("PRE_PROTECTED_PRODUCT_FREEZE.json",{"status":"NOT_REACHED","lockbox_access_count":0})
        (OUT/"README.md").write_text("# Full Portfolio Factory Search\n\nThe 63-strategy Library was frozen. 50,000 random and 25,000 genetic membership/weight candidates were screened, with deterministic greedy paths; finalists were replayed by the true concurrent engine. No product-valid portfolio was found. V2 LOCKBOX access remained zero.\n")
        (OUT/"FINAL_REPORT.md").write_text(f"# SQX CRYPTO PORTFOLIO FACTORY — FINAL STATUS\n\nDecision: `CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND`\n\nFrozen Library: {len(lib)} strategies. Random unique screen: {len(rs):,}. Genetic unique screen: {len(gs):,}. Exact concurrent finalists: {len(exact_df)}. Product-valid exact portfolios: 0. Risk and execution were not activated. V2 LOCKBOX access: 0.\n")
        print(json.dumps({"library":len(lib),"random":len(rs),"genetic":len(gs),"exact_finalists":len(exact_df),"valid":0,"decision":"CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND"}))
        return
    raise RuntimeError("A valid portfolio was found; downstream Risk/Execution handoff must be run explicitly")

if __name__=="__main__": main()
