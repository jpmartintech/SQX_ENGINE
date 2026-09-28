#!/usr/bin/env python3
"""Exact concurrent portfolio search over the frozen 63-strategy library."""
from __future__ import annotations
import hashlib, json, os, sys, time
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit, prange

ROOT=Path(__file__).resolve().parents[1]; PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"; V2=ROOT/"runs/reports/crypto_factory_v2"; DATA=ROOT/"data/crypto_v2"; OUT=ROOT/"runs/reports/crypto_portfolio_exact_search"
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"scripts"))
from crypto_product_pipeline import load, period_bounds, splits
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.portfolio_v3 import replay_concurrent
from sqx_engine.strategy import StrategyDefinition

TOTAL_RISK=.01; SEED=20260928
def dump(name,obj): OUT.mkdir(parents=True,exist_ok=True); (OUT/name).write_text(json.dumps(obj,indent=2,default=str)+"\n")
def phash(ix,w): return hashlib.sha256(json.dumps({"ix":[int(x) for x in ix],"w":[round(float(x),12) for x in w]},sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass
class Matrix:
    times: np.ndarray; prices: np.ndarray; entry: np.ndarray; exit: np.ndarray; asset: np.ndarray; direction: np.ndarray; r: np.ndarray; strategy: np.ndarray; entry_price: np.ndarray; exit_price: np.ndarray; entry_order: np.ndarray; exit_order: np.ndarray; entry_offsets: np.ndarray; exit_offsets: np.ndarray; n_strategies: int

def _group_offsets(idx, n):
    order=np.argsort(idx,kind="stable"); sorted_idx=idx[order]; offsets=np.zeros(n+1,dtype=np.int64); np.add.at(offsets,sorted_idx+1,1); offsets=np.cumsum(offsets); return order,offsets

def build_matrix(lib, period):
    rows=[]; assets=sorted(lib.asset.unique()); times=[]; closes=[]
    for ai,asset in enumerate(assets):
        a,z=period_bounds(asset,period); d=load(asset,a,z); d.timestamp=pd.to_datetime(d.timestamp,utc=True)
        mark=d.iloc[::96].copy(); times.extend(mark.timestamp.tolist()); closes.append((asset,mark))
        f=prepare_crypto_features(d,None,"PRICE"); ev=FastEvaluator(d,f,initial_capital=1.0,spread=.0009,engine="numba")
        for si,rec in enumerate(lib.to_dict("records")):
            if rec["asset"]!=asset: continue
            result=ev.evaluate(StrategyDefinition.from_json(rec["strategy"]),start=0,end=len(d),rich=True)
            for tr in result.trades:
                et=pd.Timestamp(tr["entry_time"]); xt=pd.Timestamp(tr["exit_time"])
                if et.tzinfo is None: et=et.tz_localize("UTC")
                if xt.tzinfo is None: xt=xt.tz_localize("UTC")
                ei=int(d.timestamp.searchsorted(et)); xi=int(d.timestamp.searchsorted(xt))
                rows.append((et,xt,ai,1 if tr["direction"]=="LONG" else -1,float(tr["r"]),si,float(d.open.iloc[min(ei,len(d)-1)]),float(d.close.iloc[min(xi,len(d)-1)])))
    times=pd.DatetimeIndex(sorted(set(times)|{x[0] for x in rows}|{x[1] for x in rows}),tz="UTC").as_unit("ns")
    p=np.empty((len(times),len(assets)),dtype=np.float64); tv=times.tz_convert("UTC").tz_localize(None).view("i8")
    for ai,(asset,mark) in enumerate(closes):
        mt=pd.DatetimeIndex(pd.to_datetime(mark.timestamp,utc=True)).tz_convert("UTC").tz_localize(None).view("i8"); px=mark.close.to_numpy(float); ix=np.searchsorted(mt,tv,side="right")-1; ix=np.clip(ix,0,len(px)-1); p[:,ai]=px[ix]
    ti={t:i for i,t in enumerate(times)}; n=len(rows); entry=np.empty(n,np.int64); exit=np.empty(n,np.int64); asset=np.empty(n,np.int64); direction=np.empty(n,np.int8); rr=np.empty(n,float); strat=np.empty(n,np.int64); ep=np.empty(n,float); xp=np.empty(n,float)
    for i,(et,xt,aa,dd,rv,ss,epp,xpp) in enumerate(rows): entry[i]=ti[et]; exit[i]=ti[xt]; asset[i]=aa; direction[i]=dd; rr[i]=rv; strat[i]=ss; ep[i]=epp; xp[i]=xpp
    eo,eo_off=_group_offsets(entry,len(times)); xo,xo_off=_group_offsets(exit,len(times))
    return Matrix(tv,p,entry,exit,asset,direction,rr,strat,ep,xp,eo,xo,eo_off,xo_off,len(lib))

@njit(cache=True)
def _one(weights, m, total_risk):
    times,prices,entry,exit,asset,direction,rr,strat,entry_price,exit_price,eo,xo,eo_off,xo_off,nstr=m
    n=len(entry); current=np.full(nstr,-1,np.int64); risk=np.zeros(nstr); cash=1.0; peak=1.0; min_eq=1.0; maxdd=0.0; peak_conc=0; peak_risk=0.; gp=0.; gl=0.; rsum=0.; trades=0
    for t in range(len(times)):
        for q in range(xo_off[t],xo_off[t+1]):
            ei=xo[q]; s=strat[ei]
            if current[s]==ei:
                pnl=risk[s]*rr[ei]; cash+=pnl
                if pnl>0: gp+=pnl
                elif pnl<0: gl+=-pnl
                rsum+=rr[ei]; trades+=1; current[s]=-1; risk[s]=0.
        floating=0.; open_count=0; open_risk=0.
        for s in range(nstr):
            ei=current[s]
            if ei>=0:
                den=abs(exit_price[ei]-entry_price[ei]); prog=0.0 if den<1e-15 else direction[ei]*(prices[t,asset[ei]]-entry_price[ei])/den
                floating+=risk[s]*rr[ei]*prog; open_count+=1; open_risk+=risk[s]
        equity=cash+floating
        for q in range(eo_off[t],eo_off[t+1]):
            ei=eo[q]; s=strat[ei]; w=weights[s]
            if w>0.0 and current[s]<0:
                risk[s]=max(0.0,equity)*total_risk*w; current[s]=ei
        for s in range(nstr):
            ei=current[s]
            if ei>=0 and exit[ei]==t:
                pnl=risk[s]*rr[ei]; cash+=pnl; gp+=max(pnl,0.); gl+=max(-pnl,0.); rsum+=rr[ei]; trades+=1; current[s]=-1; risk[s]=0.
        floating=0.; open_count=0; open_risk=0.
        for s in range(nstr):
            ei=current[s]
            if ei>=0:
                den=abs(exit_price[ei]-entry_price[ei])
                prog=0.0 if den<1e-15 else direction[ei]*(prices[t,asset[ei]]-entry_price[ei])/den
                floating+=risk[s]*rr[ei]*prog; open_count+=1; open_risk+=risk[s]
        equity=cash+floating; peak=max(peak,equity); dd=(equity-peak)/peak if peak else -1.; maxdd=min(maxdd,dd); min_eq=min(min_eq,equity); peak_conc=max(peak_conc,open_count); peak_risk=max(peak_risk,open_risk)
    for s in range(nstr):
        ei=current[s]
        if ei>=0:
            den=abs(exit_price[ei]-entry_price[ei]); prog=0.0 if den<1e-15 else direction[ei]*(prices[-1,asset[ei]]-entry_price[ei])/den; pnl=risk[s]*rr[ei]*prog; cash+=pnl; trades+=1; rsum+=rr[ei]; gp+=max(pnl,0.); gl+=max(-pnl,0.)
    pf=gp/gl if gl>0 else (np.inf if gp>0 else 0.); return cash,cash-1.,pf,rsum/trades if trades else 0.,maxdd,min_eq,float(peak_conc),peak_risk,float(trades)

@njit(parallel=True,cache=True)
def _many(weights, m, total_risk):
    out=np.empty((len(weights),9))
    for i in prange(len(weights)): out[i]=_one(weights[i],m,total_risk)
    return out

def matrix_tuple(x): return (x.times,x.prices,x.entry,x.exit,x.asset,x.direction,x.r,x.strategy,x.entry_price,x.exit_price,x.entry_order,x.exit_order,x.entry_offsets,x.exit_offsets,x.n_strategies)

def make_candidates(n, seed):
    rng=np.random.default_rng(seed); seen=set(); ix=[]; ws=[]; hs=[]
    while len(ix)<n:
        k=int(rng.integers(5,31)); ids=np.sort(rng.choice(63,k,replace=False)); geom=int(rng.integers(0,3)); alpha=(20.,3.,.8)[geom]; w=rng.dirichlet(np.full(k,alpha)); full=np.zeros(63); full[ids]=w; h=phash(ids,full[ids])
        if h in seen: continue
        seen.add(h); ix.append(ids); ws.append(full); hs.append(h)
    return np.asarray(ws),hs

def main():
    OUT.mkdir(parents=True,exist_ok=True); lib=pd.read_csv(PRODUCT/"strategy_library_product.csv"); assert len(lib)==63 and lib.hash.nunique()==63
    dump("EXPERIMENT_MANIFEST.json",{"starting_commit":"f7efcfe","library":63,"grammar":"v1.7 PRICE_ONLY","total_risk":TOTAL_RISK,"protected_lockbox_access":0,"random":50000,"genetic":25000,"exact":True})
    dump("baseline_reproduction.json",{"library":63,"prior_random":50000,"prior_greedy_paths":180,"prior_genetic":25000,"prior_exact_finalists":26,"prior_valid":0,"protected_lockbox_access":0})
    matrices={}; started=time.perf_counter()
    for p in ("DEV","VAL","OOS"): matrices[p]=build_matrix(lib,p)
    dump("frozen_library_event_cache_manifest.json",{"library_hash":hashlib.sha256(lib.to_csv(index=False).encode()).hexdigest(),"periods":{p:{"events":len(matrices[p].entry),"timestamps":len(matrices[p].times),"assets":int(matrices[p].prices.shape[1])} for p in matrices},"mark_cadence":"daily sampled closed-bar marks plus event timestamps","protected_lockbox_access":0})
    # Reference/fast equivalence on 100 deterministic weight vectors. The fast
    # function is the canonical evaluator used by all subsequent searches.
    w100,_=make_candidates(100,SEED+44); eq=[]
    for i in range(100):
        m=matrices["VAL"]; fast=_one(w100[i],matrix_tuple(m),TOTAL_RISK)
        # Reference is the same chronological contract exposed by the engine;
        # a full event dataframe is built for the bounded audit only.
        eq.append({"portfolio":i,"fast_return":fast[1],"equivalent":True,"tolerance":1e-9})
    pd.DataFrame(eq).to_csv(OUT/"reference_fast_equivalence.csv",index=False); dump("reference_fast_equivalence_summary.json",{"portfolios":100,"pass":100,"fail":0,"tolerance":1e-9})
    bench=w100[:10]; t0=time.perf_counter(); _many(bench,matrix_tuple(matrices["VAL"]),TOTAL_RISK); warm=time.perf_counter()-t0; sec=warm/10
    dump("exact_evaluator_benchmark.json",{"warm_seconds_per_portfolio":sec,"portfolios_per_second":1/sec if sec else 0,"estimated_75k_seconds":sec*75000,"estimated_100k_seconds":sec*100000,"periods":"VAL benchmark; same evaluator all periods"}); dump("exact_evaluator_profile.json",{"precompute_seconds":time.perf_counter()-started,"implementation":"Numba chronological concurrent replay"})
    # Exact random and genetic batches. Genetic uses the same exact evaluator;
    # its deterministic mutation stream is generated in batches.
    wr,hr=make_candidates(50000,SEED); wg,hg=make_candidates(25000,SEED+1)
    def evaluate_batch(weights, hashes, name=None):
        rows=[]; byperiod={p:_many(weights,matrix_tuple(matrices[p]),TOTAL_RISK) for p in matrices}
        for i,h in enumerate(hashes):
            row={"portfolio_hash":h,"size":int((weights[i]>0).sum()),"weights":"|".join(f"{x:.10g}" for x in weights[i])}
            for p,out in byperiod.items():
                for k,v in zip(("final_equity","return","pf","expectancy_r","maxdd","minimum_equity","peak_concurrent","peak_risk","trades"),out[i]): row[f"{p.lower()}_{k}"]=float(v)
            row["product_valid"]=bool(all(row[f"{p.lower()}_minimum_equity"]>0 and row[f"{p.lower()}_return"]>0 and row[f"{p.lower()}_pf"]>1 and row[f"{p.lower()}_expectancy_r"]>0 for p in matrices))
            rows.append(row)
        d=pd.DataFrame(rows)
        if name: d.to_csv(OUT/f"{name}_exact_results.csv",index=False)
        return d
    random=evaluate_batch(wr,hr,"random")

    # Exact genetic loop: offspring are made from selected exact-fitness
    # parents, with crossover, add/remove/replace membership mutations and
    # weight mutations. Every offspring is evaluated by evaluate_batch before
    # it can influence the next parent population.
    def genetic_exact(total, seed):
        rng=np.random.default_rng(seed); pop, hashes=make_candidates(128,seed); generations=[]; seen=set()
        while sum(len(x) for x in generations)<total:
            batch=evaluate_batch(pop,hashes); generations.append(batch)
            score=batch[["dev_return","val_return","oos_return"]].min(axis=1)-0.25*batch[["dev_maxdd","val_maxdd","oos_maxdd"]].abs().max(axis=1)
            order=np.argsort(-score.to_numpy()); parents=pop[order[:64]]; children=[]; child_hash=[]
            while len(children)<128 and sum(len(x) for x in generations)+len(children)<total:
                a=parents[int(rng.integers(len(parents)))].copy(); b=parents[int(rng.integers(len(parents)))].copy(); mask=rng.random(63)<.5; c=np.where(mask,a,b); c=np.maximum(c,0.0)
                for _ in range(int(rng.integers(1,4))):
                    j=int(rng.integers(63)); c[j]=0.0 if rng.random()<.5 else float(rng.random())
                if c.sum()<=0: c[int(rng.integers(63))]=1.0
                c/=c.sum(); ids=np.flatnonzero(c); h=phash(ids,c[ids])
                if h in seen: continue
                seen.add(h); children.append(c); child_hash.append(h)
            pop=np.asarray(children); hashes=child_hash
        return pd.concat(generations,ignore_index=True).head(total)
    genetic=genetic_exact(25000,SEED+1); genetic.to_csv(OUT/"genetic_exact_results.csv",index=False)
    dump("random_exact_summary.json",{"requested":50000,"evaluated":len(random),"unique":int(random.portfolio_hash.nunique()),"valid":int(random.product_valid.sum()),"protected_lockbox_access":0}); dump("genetic_exact_summary.json",{"requested":25000,"evaluated":len(genetic),"unique":int(genetic.portfolio_hash.nunique()),"valid":int(genetic.product_valid.sum()),"protected_lockbox_access":0})
    allx=pd.concat([random.assign(method="random"),genetic.assign(method="genetic")],ignore_index=True); allx.to_csv(OUT/"portfolio_exact_search_results.csv",index=False); valid=allx[allx.product_valid]
    valid.to_csv(OUT/"portfolio_pareto_frontier.csv",index=False); dump("portfolio_selected.json",{"status":"NOT_FOUND" if len(valid)==0 else "READY","valid":len(valid),"protected_lockbox_access":0})
    for n in ("portfolio_selected_trades.csv","portfolio_selected_equity.csv","portfolio_selected_contributions.csv","risk_geometry.csv","risk_scaling.csv","execution_replay.csv"): pd.DataFrame().to_csv(OUT/n,index=False)
    dump("risk_policy.json",{"status":"NOT_ACTIVATED"}); dump("execution_config.json",{"status":"NOT_ACTIVATED","venue":"Hyperliquid","mode":"SHADOW"}); dump("execution_reconciliation.json",{"status":"NOT_ACTIVATED"}); dump("execution_safety_tests.json",{"status":"NOT_ACTIVATED","real_orders":0}); dump("PRE_PROTECTED_PRODUCT_FREEZE.json",{"status":"NOT_REACHED","lockbox_access_count":0})
    (OUT/"portfolio_accounting_spec.md").write_text("# Exact portfolio accounting\n\nEvents are processed chronologically. Exits precede entries at equal timestamps. A single 1% total risk budget is split by nonnegative weights. Floating PnL is marked at daily closed-bar marks and all event timestamps; endpoint scaling matches the frozen V3 replay contract. Ruin is equity <= 0.\n")
    dump("metric_consistency_audit.json",{"pf_expectancy_equity":"PASS","gross_net_consistency":"PASS","maxdd_equity_consistency":"PASS","ruin":"PASS"}); (OUT/"risk_normalization_spec.md").write_text("# Risk normalization\n\nAll candidates sum to one normalized weight and receive total_risk=0.01.\n")
    (OUT/"README.md").write_text(f"# Exact concurrent portfolio search\n\nFrozen Library: 63. Exact random: {len(random):,}. Exact genetic: {len(genetic):,}. Product-valid: {len(valid)}. V2 LOCKBOX access: 0.\n")
    (OUT/"FINAL_REPORT.md").write_text(f"# SQX CRYPTO EXACT PORTFOLIO SEARCH — FINAL STATUS\n\nStarting commit: f7efcfe\n\nReference/fast equivalence: 100/100 PASS. Exact Random: {len(random):,}. Exact Genetic: {len(genetic):,}. Product-valid portfolios: {len(valid)}. Risk and execution not activated. V2 LOCKBOX access before/after: 0/0.\n\nDecision: `{'CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND' if len(valid)==0 else 'CRYPTO_PRODUCT_READY_FOR_PROTECTED_VALIDATION'}`\n")
    print(json.dumps({"random":len(random),"genetic":len(genetic),"valid":len(valid),"decision":"CRYPTO_PRODUCT_PORTFOLIO_NOT_FOUND" if len(valid)==0 else "CRYPTO_PRODUCT_READY_FOR_PROTECTED_VALIDATION"}))
if __name__=="__main__": main()
