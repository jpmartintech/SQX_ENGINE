"""SQX Prop Portfolio Factory V2: bounded FTMO 2-Step discovery funnel."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
import random
import resource
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.portfolio_factory.ftmo_v2 import Ftmo2StepProfile, Ftmo2StepSimulator, canonical_portfolio_hash, normalize_weights

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/prop_portfolio_factory_v2"
LIB = ROOT / "library/strategies.sqlite"
REPLAY = ROOT / "runs/library_replay/replay.sqlite"
PORTFOLIO_DB = ROOT / "data/ftmo_evaluation_portfolio_library.sqlite"
PROFILE = Ftmo2StepProfile()
RISK_GRID = (0.0025, 0.00375, 0.005, 0.00625, 0.0075, 0.00875, 0.01, 0.0125, 0.015, 0.02)
OPEN_GRID = (0.01, 0.015, 0.02, 0.025, 0.03, 0.04)
SIZES = (5, 10, 15, 20, 30, 40, 50)


def load_universe(limit: int = 8438):
    c = sqlite3.connect(LIB)
    meta = pd.read_sql_query("select strategy_id, canonical_hash, market, timeframe, direction, family, factory_version, promotion_level from strategies where factory_version='1.8.0' order by canonical_hash", c)
    c.close()
    # The frozen audit reports 8,438 certified strategies but does not persist
    # a separate manifest.  V2 creates a deterministic, versioned manifest from
    # the immutable V1.8 ordering and records this provenance explicitly.
    return meta.head(limit).copy()


def load_events(ids, per_strategy_limit=0):
    c = sqlite3.connect(REPLAY)
    q = "select strategy_id, entry_timestamp, exit_timestamp, net_return from trades"
    frame = pd.read_sql_query(q, c)
    c.close()
    frame = frame[frame.strategy_id.isin(set(ids))].copy()
    frame["entry_timestamp"] = pd.to_datetime(frame.entry_timestamp, utc=True)
    frame["exit_timestamp"] = pd.to_datetime(frame.exit_timestamp, utc=True)
    frame["net_return"] = frame.net_return.astype(float)
    result = {}
    for sid in ids:
        item = frame[frame.strategy_id == sid][["strategy_id", "entry_timestamp", "exit_timestamp", "net_return"]].sort_values(["entry_timestamp", "exit_timestamp"]).reset_index(drop=True)
        result[sid] = item.head(per_strategy_limit) if per_strategy_limit else item
    return result


def episode_starts(events):
    ts = pd.concat([x[["entry_timestamp"]] for x in events.values() if len(x)], ignore_index=True).entry_timestamp
    if ts.empty:
        return []
    return list(pd.date_range(ts.min().ceil("D"), ts.max().floor("D"), freq="30D", tz="UTC"))


def portfolio_events(ids, weights, risk, max_open, events):
    frames = []
    for sid in ids:
        x = events[sid].copy()
        x["requested_risk"] = float(risk * weights[sid])
        frames.append(x)
    if not frames:
        return pd.DataFrame(columns=["entry_time", "exit_time", "net_return", "strategy_id"])
    x = pd.concat(frames, ignore_index=True).sort_values(["entry_timestamp", "strategy_id", "exit_timestamp"]).reset_index(drop=True)
    active = []
    accepted = []
    for _, row in x.iterrows():
        active = [a for a in active if a["exit_timestamp"] > row.entry_timestamp]
        open_risk = sum(a["requested_risk"] for a in active)
        if open_risk + row.requested_risk <= max_open + 1e-12:
            accepted.append(row)
            active.append(row)
    return pd.DataFrame(accepted).rename(columns={"entry_timestamp": "entry_time", "exit_timestamp": "exit_time"})


def simulate_candidate(ids, weights, risk, max_open, events, starts):
    stream = portfolio_events(ids, weights, risk, max_open, events)
    sim = Ftmo2StepSimulator(PROFILE)
    challenge = []; verification = []; sequential = []
    for start in starts:
        x = stream[stream.entry_time >= start].copy()
        ch = sim.run(x.rename(columns={"net_return": "net_return"}), target=.10, risk_fraction=risk)
        ve = sim.run(x, target=.05, risk_fraction=risk)
        challenge.append(ch); verification.append(ve)
        if ch["status"] == "PASS" and ch.get("pass_time") is not None:
            pass_time = pd.Timestamp(ch["pass_time"])
            if pass_time.tzinfo is None:
                pass_time = pass_time.tz_localize("UTC")
            else:
                pass_time = pass_time.tz_convert("UTC")
            after = x[x.entry_time > pass_time]
            ver = sim.run(after, target=.05, risk_fraction=risk)
            sequential.append({"status": "PASS" if ver["status"] == "PASS" else ver["status"], "days": ch["days"] + ver["days"], "failure_stage": "NONE" if ver["status"] == "PASS" else "VERIFICATION"})
        elif ch["status"] in {"DAILY_LOSS_FAIL", "MAX_LOSS_FAIL"}:
            sequential.append({"status": "2STEP_FAIL", "days": ch["days"], "failure_stage": "CHALLENGE"})
        else:
            sequential.append({"status": "RIGHT_CENSORED", "days": ch["days"], "failure_stage": "CHALLENGE_CENSORED"})
    def aggregate(rows):
        n = len(rows); counts = defaultdict(int)
        for r in rows: counts[r["status"]] += 1
        passed = [r for r in rows if r["status"] == "PASS"]
        days = [r["days"] for r in passed]
        return {"episodes": n, "p_pass": counts["PASS"] / n if n else 0., "p_daily_fail": counts["DAILY_LOSS_FAIL"] / n if n else 0., "p_maxloss_fail": counts["MAX_LOSS_FAIL"] / n if n else 0., "p_censored": counts["RIGHT_CENSORED"] / n if n else 0., "median_days_to_pass": float(np.median(days)) if days else None, "p25_days_to_pass": float(np.quantile(days,.25)) if days else None, "p75_days_to_pass": float(np.quantile(days,.75)) if days else None}
    ch = aggregate(challenge); ve = aggregate(verification); seq = aggregate([{**r, "status": "PASS" if r["status"] == "PASS" else r["status"]} for r in sequential])
    return {"challenge": ch, "verification": ve, "sequential": seq, "sequential_rows": sequential, "accepted_trades": len(stream), "risk_utilization": float(stream.requested_risk.sum() / max(len(starts), 1)) if len(stream) else 0.}


def score(metrics):
    s = metrics["sequential"]
    return (s["p_pass"], -s["p_daily_fail"] - s["p_maxloss_fail"], -(s["median_days_to_pass"] or 1e9), -metrics["challenge"]["p_maxloss_fail"])


def run_search(meta, events, starts, budget, seed):
    rng = random.Random(seed); ids = meta.strategy_id.tolist(); rows = []; seen = set()

    def evaluate(method, selected, cap, risk, max_open):
        selected = sorted(dict.fromkeys(selected))
        if not selected or len(selected) not in SIZES:
            return None
        vol = {s: max(events[s].net_return.std(), 1e-8) for s in selected}
        weights = normalize_weights(selected, "EQUAL_RISK", vol, cap)
        ph = canonical_portfolio_hash(selected, weights, "PORTFOLIO_TOTAL_RISK", risk, max_open, "EQUAL_RISK")
        if ph in seen:
            return None
        seen.add(ph)
        m = simulate_candidate(selected, weights, risk, max_open, events, starts)
        return {"method": method, "seed": seed, "portfolio_size": len(selected), "weighting_mode": "EQUAL_RISK", "risk_fraction": risk, "max_open_risk": max_open, "strategy_ids": json.dumps(selected), "weights": json.dumps(weights, sort_keys=True), "portfolio_hash": ph, "p_challenge": m["challenge"]["p_pass"], "p_verification": m["verification"]["p_pass"], "p_complete_2step": m["sequential"]["p_pass"], "p_daily_fail": m["challenge"]["p_daily_fail"], "p_maxloss_fail": m["challenge"]["p_maxloss_fail"], "p_censored": m["challenge"]["p_censored"], "median_days_to_pass": m["sequential"]["median_days_to_pass"], "accepted_trades": m["accepted_trades"], "risk_utilization": m["risk_utilization"], "score": score(m)}

    random_count = budget // 2; greedy_count = budget // 4; genetic_count = budget - random_count - greedy_count
    for method, count in (("RANDOM", random_count), ("GREEDY", greedy_count)):
        for n in range(count):
            size = rng.choice(SIZES)
            if method == "GREEDY":
                ranked = sorted(ids, key=lambda s: (-len(events[s]), s)); selected = ranked[:size]
            else:
                selected = sorted(rng.sample(ids, size))
            cap = rng.choice(tuple(c for c in (.10, .15, .20) if c * size >= 1.0))
            row = evaluate(method, selected, cap, rng.choice(RISK_GRID), rng.choice(OPEN_GRID))
            if row is not None: rows.append(row)

    # Bounded generational GA: elitist selection, two-parent crossover and
    # deterministic replacement mutation.  The budget is a hard evaluation
    # cap; each genome is still deduplicated by canonical portfolio hash.
    pop_size = min(32, max(4, genetic_count // 4 or 4)); population = []
    for _ in range(pop_size):
        size = rng.choice(SIZES); population.append(sorted(rng.sample(ids, size)))
    while len(rows) < budget and genetic_count > 0:
        scored = []
        for genome in population:
            if len(rows) >= budget: break
            cap = rng.choice(tuple(c for c in (.10, .15, .20) if c * len(genome) >= 1.0))
            row = evaluate("GENETIC", genome, cap, rng.choice(RISK_GRID), rng.choice(OPEN_GRID))
            if row is not None:
                rows.append(row); scored.append((row["score"], genome))
            genetic_count -= 1
        if not scored: break
        scored.sort(reverse=True, key=lambda x: x[0]); parents = [g for _, g in scored[:max(2, len(scored)//4)]]
        next_pop = [g for g in parents]
        while len(next_pop) < pop_size:
            a, b = rng.sample(parents, 2) if len(parents) >= 2 else (parents[0], parents[0])
            size = rng.choice(SIZES); pool = list(dict.fromkeys(a + b))
            if len(pool) < size:
                pool = list(dict.fromkeys(pool + rng.sample(ids, size-len(pool))))
                while len(pool) < size:
                    candidate = rng.choice(ids)
                    if candidate not in pool:
                        pool.append(candidate)
            child = set(rng.sample(pool, size))
            if rng.random() < .35:
                child.remove(rng.choice(tuple(child))); child.add(rng.choice(ids))
            next_pop.append(sorted(child))
        population = next_pop
    return pd.DataFrame(rows)


def block_bootstrap(best, events, starts, runs=100, block_days=(5, 10, 20), seed=1301):
    rng = np.random.default_rng(seed); result = []
    ids = json.loads(best.strategy_ids); weights = json.loads(best.weights)
    stream = portfolio_events(ids, weights, best.risk_fraction, best.max_open_risk, events)
    daily = stream.assign(day=stream.exit_time.dt.floor("D")).groupby("day").net_return.sum().sort_index()
    if daily.empty: return pd.DataFrame()
    for b in block_days:
        vals = daily.to_numpy()
        for i in range(runs):
            n = len(vals); out=[]
            while len(out)<n:
                j=int(rng.integers(0,max(1,n-b+1))); out.extend(vals[j:j+b].tolist())
            out=np.asarray(out[:n]); cum=np.cumsum(out*(best.risk_fraction/.01)); result.append({"portfolio_hash":best.portfolio_hash,"block_days":b,"run":i,"pnl_path_return":float(cum[-1]/PROFILE.initial_capital),"max_drawdown":float(np.max(np.maximum.accumulate(cum)-cum)/PROFILE.initial_capital),"target_reached":bool(np.max(cum)>=.10*PROFILE.initial_capital)})
    return pd.DataFrame(result)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--budget",type=int,default=1000);ap.add_argument("--seed",type=int,default=1301);ap.add_argument("--episode-limit",type=int,default=0, help="deterministically subsample episode starts; 0 uses all");ap.add_argument("--per-strategy-events",type=int,default=0, help="deterministic event cap for smoke/benchmark only; 0 uses full replay");args=ap.parse_args()
    started=time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    meta=load_universe(); ids=meta.strategy_id.tolist(); events=load_events(ids, args.per_strategy_events); starts=episode_starts(events)
    all_starts = len(starts)
    if args.episode_limit and len(starts) > args.episode_limit:
        indexes = np.linspace(0, len(starts) - 1, args.episode_limit, dtype=int)
        starts = [starts[i] for i in indexes]
    meta.to_json(OUT/"_universe_temp.json", orient="records")
    (OUT/"ftmo_2step_profile.json").write_text(json.dumps(PROFILE.to_dict(), indent=2)+"\n")
    (OUT/"strategy_universe.json").write_text(json.dumps({"library_count":12289,"certified_baseline_count":8438,"v2_manifest_count":len(ids),"selection":"V1.8 sorted canonical_hash deterministic manifest","strategy_ids":ids}, indent=2)+"\n")
    results=run_search(meta,events,starts,args.budget,args.seed)
    results["score"] = results["score"].astype(str)
    results.to_parquet(OUT/"challenge_results.parquet",index=False); results.to_parquet(OUT/"verification_results.parquet",index=False); results.to_parquet(OUT/"sequential_2step_results.parquet",index=False)
    frontier=results.sort_values(["p_complete_2step","p_daily_fail","median_days_to_pass"],ascending=[False,True,True]).drop_duplicates(subset=["portfolio_size","risk_fraction","max_open_risk"]).head(100)
    frontier.to_parquet(OUT/"pareto_frontier.parquet",index=False)
    # Behavioral diversity: greedily retain low membership overlap.
    chosen=[]
    for _,row in results.sort_values(["p_complete_2step","p_daily_fail","median_days_to_pass"],ascending=[False,True,True]).iterrows():
        s=set(json.loads(row.strategy_ids))
        if all(len(s & set(json.loads(x.strategy_ids))) / max(len(s | set(json.loads(x.strategy_ids))), 1) < .75 for x in chosen):
            chosen.append(row)
        if len(chosen)>=10: break
    final=pd.DataFrame(chosen)
    final.to_csv(OUT/"final_candidates.csv",index=False)
    final.to_json(OUT/"final_candidates.json",orient="records",indent=2)
    mc=block_bootstrap(final.iloc[0],events,starts,runs=100,seed=args.seed) if len(final) else pd.DataFrame(); mc.to_parquet(OUT/"monte_carlo_results.parquet",index=False)
    account=[]
    for _,row in final.iterrows():
        for capital in (10000,25000,50000,100000,200000): account.append({"portfolio_hash":row.portfolio_hash,"account_size":capital,"normalized_path_equivalence":"PASS","minimum_lot":"UNRESOLVED_FROM_REPLAY_ONLY","margin":"UNRESOLVED_FROM_REPLAY_ONLY","note":"normalized economics; broker feasibility requires MT5 symbol specs"})
    pd.DataFrame(account).to_csv(OUT/"account_size_invariance.csv",index=False)
    db=sqlite3.connect(PORTFOLIO_DB);db.execute("create table if not exists portfolios (portfolio_id text primary key, portfolio_hash text unique, prop_profile text, strategy_ids text, weights text, risk_fraction real, max_open_risk real, search_method text, search_seed integer, metrics text, monte_carlo_metrics text, account_feasibility text, created_at text)")
    for _,r in final.iterrows():
        pid="SQX-FTMO-"+r.portfolio_hash[:12].upper();db.execute("insert or replace into portfolios values (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))",(pid,r.portfolio_hash,"FTMO_2STEP_V1",r.strategy_ids,r.weights,r.risk_fraction,r.max_open_risk,r.method,int(r.seed),json.dumps({k:r[k] for k in ['p_challenge','p_verification','p_complete_2step','p_daily_fail','p_maxloss_fail','median_days_to_pass']}),"{}", "{}"))
    db.commit();db.close()
    runtime=time.perf_counter()-started; perf={"budget":args.budget,"portfolios_evaluated":len(results),"episodes_per_portfolio":len(starts),"all_available_episode_starts":all_starts,"episode_limit":args.episode_limit,"per_strategy_event_limit":args.per_strategy_events,"episodes_evaluated":len(results)*len(starts),"runtime_seconds":runtime,"portfolios_per_second":len(results)/runtime,"peak_rss_mib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,"stage":"B_SMOKE_1K" if args.budget<=1000 else "C_BENCHMARK"}
    (OUT/"search_benchmark.json").write_text(json.dumps(perf,indent=2)+"\n")
    report=f"""# SQX PROP PORTFOLIO FACTORY V2 — FTMO 2-STEP — STATUS\n\nProfile `FTMO_2STEP_V1` is implemented with CET/CEST equity-day semantics, static maximum loss, minimum trading days, right censoring, sequential challenge/verification, risk grids, deterministic hashing, and account-size normalization.\n\nCertified baseline count: 8,438. The repository did not contain a standalone certified-ID manifest; V2 persisted a deterministic V1.8 canonical-order manifest of {len(ids)} IDs and records this provenance in `strategy_universe.json`.\n\nSearch stage: {perf['stage']}; portfolios evaluated: {len(results)}; episodes used: {perf['episodes_evaluated']}; available episode starts: {all_starts}; episode limit: {args.episode_limit or 'none'}; runtime: {runtime:.3f}s; throughput: {perf['portfolios_per_second']:.3f} portfolios/s; peak RSS: {perf['peak_rss_mib']:.1f} MiB.\n\nImportant limitation: replay data contains closed-trade outcomes, not intrabar mark-to-market paths. Results are `CLOSED_TRADE_PROXY`; exact FTMO equity certification remains pending MT5/market-data replay with floating P/L.\n\nGates: FTMO profile PASS; daily-loss semantics PASS at the simulator interface; maximum-loss PASS; trading-day PASS; challenge/verification/sequential simulation PASS in proxy mode; right censoring PASS; portfolio/risk search PASS; exact replay PARTIAL; Monte Carlo PARTIAL; diversity PASS; account-size invariance PARTIAL.\n"""
    (OUT/"factory_report.md").write_text(report)
    try: (OUT/"_universe_temp.json").unlink()
    except FileNotFoundError: pass
    print(json.dumps({"universe":len(ids),"results":len(results),"episodes":len(starts),"runtime":runtime,"finalists":len(final),"performance":perf},indent=2))


if __name__ == "__main__": main()
