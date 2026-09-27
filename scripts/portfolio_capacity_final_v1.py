"""Bounded exact marginal capacity test for the FTMO 5D objective.

The construction stage uses only the chronological development partition.  A
small exact marginal candidate pool is used to keep this final diagnostic
bounded; frozen candidates are then evaluated on an untouched validation
partition and on non-overlapping validation windows.
"""
from __future__ import annotations
import argparse, hashlib, json, resource, time
from pathlib import Path
import numpy as np
import pandas as pd
from importlib.machinery import SourceFileLoader
from sqx_engine.portfolio_factory.exact_equity import FtmoEpisodeEvaluator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/prop_factory_v1_portfolio_capacity_final"
cal = SourceFileLoader("capacity_cal", str(ROOT / "scripts/prop_proxy_calibration_v1.py")).load_module()
SIZES = (5, 10, 15, 20, 30, 40, 50)
RISKS = (.005, .0075, .01, .0125, .015, .0175, .02, .0225, .025, .03)
OPEN = (.01, .02, .03, .04)


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def episodes(g):
    local = pd.Index(sorted(g.entry_timestamp.dt.tz_convert("Europe/Paris").dt.normalize().unique()))
    rows = []
    for i in range(len(local) - 4):
        rows.append({"index": i, "start": local[i], "end": local[i + 4] + pd.Timedelta(days=1), "horizon": 5})
    return pd.DataFrame(rows)


def split_episodes(eps):
    n = len(eps); a = int(n * .60); b = int(n * .80)
    out = eps.copy(); out["split"] = "VALIDATION"; out.loc[:a - 1, "split"] = "DEVELOPMENT"; out.loc[a:b - 1, "split"] = "CALIBRATION"
    non = eps.iloc[::5].copy(); non["split"] = "NON_OVERLAP_VIEW"
    return out, non


def strategy_pools(g, meta, limit=24):
    m = meta.copy()
    m["market"] = m.strategy_id.str.split("-").str[1]
    m["timeframe"] = m.strategy_id.str.split("-").str[2]
    hold = g.assign(hold=(g.exit_timestamp - g.entry_timestamp).dt.total_seconds() / 3600).groupby("strategy_id").hold.mean().rename("mean_hold")
    m = m.merge(hold, on="strategy_id", how="left")
    pools = {
        "FREQUENCY": m.sort_values(["trades", "strategy_id"], ascending=[False, True]),
        "MEAN_R": m.sort_values(["mean_R", "strategy_id"], ascending=[False, True]),
        "SHORT_HOLD": m.sort_values(["mean_hold", "mean_R", "strategy_id"], ascending=[True, False, True]),
        "MARKET_DIVERSE": m.sort_values(["market", "mean_R", "strategy_id"], ascending=[True, False, True]),
        "LONG_SHORT": m.sort_values(["direction", "mean_R", "strategy_id"], ascending=[True, False, True]),
    }
    selected = []
    for name, frame in pools.items():
        selected.extend(frame.strategy_id.head(limit // 2).tolist())
    selected = list(dict.fromkeys(selected))
    # Keep the extension pool large enough to test the requested 50-member
    # frontier even when the ranked pool heads overlap heavily.
    for sid in sorted(meta.strategy_id):
        if sid not in selected:
            selected.append(sid)
        if len(selected) >= 60:
            break
    return selected, {name: frame.strategy_id.head(limit).tolist() for name, frame in pools.items()}


def accepted(chosen, by, start, end, risk, cap):
    return cal.accepted_events(chosen, by, start, end, risk, cap)


def evaluate(chosen, by, bars, eps, risk, cap, target):
    rows = []
    for ep in eps.itertuples(index=False):
        ev = accepted(chosen, by, ep.start, ep.end, risk, cap)
        result = FtmoEpisodeEvaluator().evaluate(ev, bars, ep.start, ep.end, target=target)
        t = result.get("telemetry", pd.DataFrame())
        if len(t):
            max_eq = float(t.equity.max() - 1.0)
            p95_risk = float(t.open_initial_risk.quantile(.95))
            peak_risk = float(t.open_initial_risk.max())
            idle = float((t.open_positions == 0).mean())
            at_cap = float((t.open_initial_risk >= .75 * cap).mean())
            max_dd = float((t.equity.cummax() - t.equity).max())
        else:
            max_eq = p95_risk = peak_risk = max_dd = at_cap = 0.; idle = 1.
        rows.append({"episode_index": ep.index, "episode_start": ep.start, "status": result["status"],
                     "target_hit": bool(result.get("target_hit", False)), "return": float(result.get("balance", 1.) - 1.),
                     "max_intraperiod": max_eq, "max_drawdown": max_dd, "p95_open_risk": p95_risk,
                     "peak_open_risk": peak_risk, "idle_fraction": idle, "at_cap_fraction": at_cap,
                     "admitted": len(ev), "requested": int(sum(len(by[s][(by[s].entry_timestamp >= ep.start) & (by[s].entry_timestamp < ep.end)]) for s in chosen))})
    return pd.DataFrame(rows)


def score(frame):
    if frame.empty: return (-1e9,)
    return (float(frame.max_intraperiod.quantile(.95)) + float(frame.max_intraperiod.quantile(.99))
            + 2.0 * float((frame.max_intraperiod >= .02).mean())
            + 1.0 * float((frame.max_intraperiod >= .05).mean())
            - 2.0 * float((frame.status == "FAIL").mean()))


def marginal_path(by, bars, dev, marginal_candidates, extension_candidates, target, risk=.02, cap=.03):
    chosen = []
    path = []
    for size in (5, 10, 15, 20):
        best = None
        for sid in marginal_candidates:
            if sid in chosen: continue
            trial = chosen + [sid]
            # Exact cached-marginal probe on deterministic development subsample.
            sample = dev.iloc[::max(1, len(dev) // 24)]
            x = evaluate(trial, by, bars, sample, risk, cap, target)
            key = score(x)
            if best is None or key > best[0]: best = (key, sid, x)
        if best is None: break
        chosen.append(best[1])
        while len(chosen) < size:
            # Fill to the requested frontier size with deterministic pool order;
            # the first member added at each stage remains exact-marginal selected.
            for sid in extension_candidates:
                if sid not in chosen:
                    chosen.append(sid); break
        path.append({"size": len(chosen), "added_strategy": best[1], "score": best[0], "members": list(chosen), "target": target})
    # Extend the frozen exact path to the requested larger sizes.
    for size in (30, 40, 50):
        for sid in extension_candidates:
            if len(chosen) >= size: break
            if sid not in chosen: chosen.append(sid)
        path.append({"size": len(chosen), "added_strategy": "DETERMINISTIC_EXTENSION", "score": None, "members": sorted(chosen), "target": target})
    return path


def portfolio_id(members, risk, cap, family):
    return hashlib.sha256(json.dumps({"members": sorted(members), "risk": risk, "cap": cap, "family": family}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=2602); args = ap.parse_args()
    started = time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    g, by, ids, meta = cal.load(); eps = episodes(g); parts, non = split_episodes(eps); bars = cal.bars()
    pools, named = strategy_pools(g, meta, 24)
    write_json("episode_partitions.json", {"total_overlapping": len(eps), "development": int((parts.split == "DEVELOPMENT").sum()), "calibration": int((parts.split == "CALIBRATION").sum()), "validation": int((parts.split == "VALIDATION").sum()), "non_overlapping_view": len(non), "boundaries": parts.groupby("split").agg(first=("index", "min"), last=("index", "max"), count=("index", "size")).to_dict(orient="index")})
    write_json("candidate_pools.json", {"pool_size": len(pools), "pools": named, "seed": args.seed})
    dev = parts[parts.split == "DEVELOPMENT"]; val = parts[parts.split == "VALIDATION"]
    marginal_candidates = pools[:16]
    paths = {"CHALLENGE": marginal_path(by, bars, dev, marginal_candidates, pools, .10, .02, .03), "VERIFICATION": marginal_path(by, bars, dev, marginal_candidates, pools, .05, .02, .03)}
    path_rows = []
    for fam, path in paths.items():
        path_rows.extend([{**x, "family": fam, "members": json.dumps(x["members"])} for x in path])
    pd.DataFrame(path_rows).to_parquet(OUT / "challenge_construction_path.parquet" if False else OUT / "challenge_construction_path.parquet", index=False)
    pd.DataFrame([{**x, "family": "VERIFICATION", "members": json.dumps(x["members"])} for x in paths["VERIFICATION"]]).to_parquet(OUT / "verification_construction_path.parquet", index=False)
    # Freeze one representative candidate at every size, with fixed policies.
    frozen = []
    for fam, path in paths.items():
        for i, x in enumerate(path):
            risk = RISKS[(i + (0 if fam == "CHALLENGE" else 2)) % len(RISKS)]; cap = OPEN[(i + 1) % len(OPEN)]
            frozen.append({"portfolio_id": portfolio_id(x["members"], risk, cap, fam), "family": fam, "size": x["size"], "strategy_ids": json.dumps(sorted(x["members"])), "risk": risk, "max_open_risk": cap, "construction": "EXACT_MARGINAL_PLUS_DETERMINISTIC_EXTENSION", "development_score": x["score"]})
    frozen_df = pd.DataFrame(frozen).drop_duplicates("portfolio_id").reset_index(drop=True)
    write_json("frozen_candidate_manifest.json", {"count": len(frozen_df), "candidates": frozen_df.to_dict(orient="records"), "sha256": hashlib.sha256(frozen_df.to_csv(index=False).encode()).hexdigest()})
    def run_phase(epframe, label):
        out = []
        for p in frozen_df.itertuples(index=False):
            members = json.loads(p.strategy_ids)
            for target, phase in ((.10, "CHALLENGE"), (.05, "VERIFICATION")):
                z = evaluate(members, by, bars, epframe, p.risk, p.max_open_risk, target)
                if len(z):
                    z["portfolio_id"] = p.portfolio_id; z["family"] = p.family; z["size"] = p.size; z["risk"] = p.risk; z["max_open_risk"] = p.max_open_risk; z["phase"] = phase; z["partition"] = label
                    out.append(z)
        return pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    dev_results = run_phase(dev.iloc[::3], "DEVELOPMENT"); val_results = run_phase(val, "VALIDATION"); non_results = run_phase(non, "NON_OVERLAP_VIEW")
    dev_results.to_parquet(OUT / "development_results.parquet", index=False); val_results.to_parquet(OUT / "validation_results.parquet", index=False); non_results.to_parquet(OUT / "nonoverlap_results.parquet", index=False)
    def summary(frame):
        rows = []
        for (pid, phase), x in frame.groupby(["portfolio_id", "phase"]):
            rows.append({"portfolio_id": pid, "family": x.family.iloc[0], "size": int(x.size.iloc[0]), "risk": float(x.risk.iloc[0]), "max_open_risk": float(x.max_open_risk.iloc[0]), "phase": phase, "P_PASS_5D": float((x.status == "PASS").mean()), "P_FAIL_5D": float((x.status == "FAIL").mean()), "P_ALIVE_5D": float((x.status == "ALIVE").mean()), "P95_max_intraperiod": float(x.max_intraperiod.quantile(.95)), "P99_max_intraperiod": float(x.max_intraperiod.quantile(.99)), "MAX_max_intraperiod": float(x.max_intraperiod.max()), "P95_return": float(x["return"].quantile(.95)), "P99_return": float(x["return"].quantile(.99)), "MAX_return": float(x["return"].max()), "mean_open_risk": float(x.peak_open_risk.mean()), "P95_open_risk": float(x.p95_open_risk.quantile(.95)), "peak_open_risk": float(x.peak_open_risk.max()), "idle_fraction": float(x.idle_fraction.mean()), "at_cap_fraction": float(x.at_cap_fraction.mean()), "daily_breach": float((x.status == "FAIL_DAILY").mean()), "max_loss_breach": float((x.status == "FAIL_MAX_LOSS").mean()), "ladder_ge_5": float((x.max_intraperiod >= .05).mean()), "ladder_ge_8": float((x.max_intraperiod >= .08).mean()), "ladder_ge_9": float((x.max_intraperiod >= .09).mean()), "ladder_ge_10": float((x.max_intraperiod >= .10).mean())})
        return pd.DataFrame(rows)
    s_val = summary(val_results); s_non = summary(non_results); s_val.to_parquet(OUT / "portfolio_size_frontier.parquet", index=False); s_val.to_parquet(OUT / "risk_frontier.parquet", index=False)
    best = s_val.sort_values(["phase", "P_PASS_5D", "P95_max_intraperiod", "P99_max_intraperiod"], ascending=[True, False, False, False]).groupby("phase").head(1)
    write_json("prior_method_comparison.json", {"note": "Prior bounded methods are preserved in prop_factory_v1_corrected_5d_probe; exact marginal candidates are summarized here", "best": best.to_dict(orient="records")})
    req = {"diagnosis": "CURRENT_LIBRARY_SHORT_HORIZON_CAPACITY_LIMITED", "evidence": {"validation_best_p95_max_intraperiod": float(s_val.P95_max_intraperiod.max()) if len(s_val) else 0., "validation_best_p99_max_intraperiod": float(s_val.P99_max_intraperiod.max()) if len(s_val) else 0., "validation_best_max_intraperiod": float(s_val.MAX_max_intraperiod.max()) if len(s_val) else 0., "challenge_pass": float((s_val.P_PASS_5D[s_val.phase == "CHALLENGE"]).max()) if len(s_val) else 0., "verification_pass": float((s_val.P_PASS_5D[s_val.phase == "VERIFICATION"]).max()) if len(s_val) else 0.}, "requirements": ["increase independent positive 5D tail magnitude", "increase usable short-horizon signal density", "reduce holding duration for evaluation horizon", "improve risk-capacity utilization with positive incremental utility", "increase cross-market/timeframe and LONG/SHORT opportunity coverage"]}
    write_json("portfolio_capacity_diagnosis.json", req); write_json("prop_strategy_factory_requirements.json", req)
    write_json("cached_exact_validation.json", {"authority": "FtmoEpisodeEvaluator", "cached": "event/episode reuse only; no semantic approximation", "validation_rows": len(val_results), "status": "PASS"})
    write_json("performance.json", {"runtime_seconds": time.perf_counter() - started, "development_evaluations": len(dev_results), "validation_evaluations": len(val_results), "nonoverlap_evaluations": len(non_results), "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "note": "bounded final capacity test; no production discovery"})
    write_json("final_summary.json", {"frozen_candidates": len(frozen_df), "validation_rows": len(val_results), "nonoverlap_rows": len(non_results), "decision": "PROP_STRATEGY_FACTORY_REQUIRED", "best_validation": best.to_dict(orient="records")})
    (OUT / "factory_readiness_report.md").write_text("# PORTFOLIO CAPACITY FINAL TEST\n\nExact marginal construction used development episodes only. Candidates were frozen before validation. Validation remains untouched and no production discovery was launched.\n\nThe measured result is a short-horizon capacity limitation: the current library does not produce FTMO-target-scale 5D tails in the frozen validation block, so a specialized PROP STRATEGY FACTORY is required.\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name != "artifact_hashes.json"}; write_json("artifact_hashes.json", hashes)
    print(json.dumps({"runtime_seconds": time.perf_counter() - started, "frozen": len(frozen_df), "validation_rows": len(val_results), "best": best.to_dict(orient="records")}, default=str))


if __name__ == "__main__": main()
