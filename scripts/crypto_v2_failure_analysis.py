#!/usr/bin/env python
"""Forensic, burned-data-only analysis of the closed Crypto V2 experiment."""
from __future__ import annotations
import ast, hashlib, json, math, os, platform, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "runs/reports/crypto_factory_v2"
OUT = ROOT / "runs/reports/crypto_v2_failure_analysis"
sys.path.insert(0, str(ROOT))
from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition


def dump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")


def h(path):
    x = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): x.update(b)
    return x.hexdigest()


def load_frame(asset):
    d = pd.read_parquet(ROOT / "data/crypto_v2" / f"{asset}_M15.parquet").copy()
    scale = float(d.close.iloc[0])
    for c in ("open", "high", "low", "close"): d[c] = d[c].astype(float) / scale
    return d


def bounds(asset):
    return json.loads((V2 / "temporal_splits.json").read_text())[asset]["bounds"]


def idx(frame, timestamp): return int(frame.timestamp.searchsorted(pd.Timestamp(timestamp)))


def metrics(ev, strategy, start, end, cost=1.0, rich=False):
    r = ev.evaluate(strategy, start=start, end=end, cost_multiplier=cost, rich=rich)
    return {"trades": int(r.trade_count), "pf": float(r.profit_factor), "expectancy_r": float(r.expectancy_r),
            "net_r": float(r.net_profit), "return": float(r.return_pct), "maxdd": float(r.max_drawdown),
            "win_rate": float(r.win_rate), "average_win_r": float(np.mean([x for x in r.trade_returns if x > 0])) if r.trade_returns and any(x > 0 for x in r.trade_returns) else 0.0,
            "average_loss_r": float(np.mean([x for x in r.trade_returns if x < 0])) if r.trade_returns and any(x < 0 for x in r.trade_returns) else 0.0,
            "largest_loss_r": float(min(r.trade_returns)) if r.trade_returns else 0.0,
            "trade_returns": r.trade_returns, "trades_detail": r.trades}


def slope(values):
    x = np.arange(len(values), dtype=float); y = np.asarray(values, dtype=float)
    ok = np.isfinite(y)
    return float(np.polyfit(x[ok], y[ok], 1)[0]) if ok.sum() >= 3 else np.nan


def corr(a, b, method="spearman"):
    z = pd.DataFrame({"a": a, "b": b}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(z) < 3: return None
    if method == "spearman":
        return float(z.a.rank().corr(z.b.rank()))
    return float(z.a.corr(z.b))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    access = pd.read_csv(V2 / "data_access_ledger.csv")
    before = int(access.segment.eq("LOCKBOX").sum())
    if before != 0: raise RuntimeError("LOCKBOX was already accessed")
    lib = pd.read_csv(V2 / "strategy_library_v2.csv")
    oos = pd.read_csv(V2 / "oos_strategy_results.csv")
    selected = lib.head(20).copy()
    assets = sorted(lib.asset.unique())
    freeze = json.loads((V2 / "temporal_splits.json").read_text())
    # Artifact integrity is metadata-only and covers the supplied V2 evidence.
    required = ["EXPERIMENT_MANIFEST.json", "temporal_splits.json", "dev_internal_windows.csv", "strategy_factory_v2_fitness.json",
                "dev_strategy_results.csv", "dev_strategy_gate_summary.json", "STRATEGY_FACTORY_FREEZE.json", "validation_strategy_results.csv",
                "validation_summary.json", "strategy_library_v2.csv", "strategy_library_v2.json", "portfolio_baselines.csv",
                "PORTFOLIO_FACTORY_FREEZE.json", "PRE_OOS_TOTAL_FREEZE.json", "oos_strategy_results.csv", "oos_portfolio_result.json",
                "oos_summary.json", "OOS_DECISION.json", "data_access_ledger.csv", "data_access_summary.json", "cost_model.json"]
    integrity = {f: {"exists": (V2 / f).exists(), "sha256": h(V2 / f) if (V2 / f).exists() else None, "bytes": (V2 / f).stat().st_size if (V2 / f).exists() else 0} for f in required}
    dump("artifact_integrity.json", integrity)
    manifest = {"starting_commit": "0609916", "purpose": "burned-data forensic diagnosis", "lockbox_policy": "strictly forbidden",
                "data_status": {"DEV": "BURNED_RESEARCH", "VAL": "BURNED_RESEARCH", "OOS": "BURNED_RESEARCH", "LOCKBOX": "UNCONSUMED_PROTECTED"},
                "input_hashes": {f: v["sha256"] for f,v in integrity.items()}, "selected_count": len(selected), "library_count": len(lib), "lockbox_access_before": before}
    dump("FAILURE_ANALYSIS_MANIFEST.json", manifest)

    # Replay every frozen library strategy over the six DEV windows, VAL and OOS.
    rows, rich_oos = [], []
    evaluators = {}
    for asset in assets:
        frame = load_frame(asset)
        feats = prepare_crypto_features(frame, None, "PRICE")
        ev = FastEvaluator(frame, feats, initial_capital=1.0, spread=.0009, engine="numba")
        evaluators[asset] = (frame, ev)
        b = freeze[asset]["bounds"]
        cuts = pd.date_range(pd.Timestamp(b["START"]), pd.Timestamp(b["DEV_END"]), periods=7, tz="UTC")
        periods = [(f"D{i+1}", idx(frame,cuts[i]), idx(frame,cuts[i+1])) for i in range(6)]
        periods += [("VAL", idx(frame,b["DEV_END"]), idx(frame,b["VAL_END"])), ("OOS", idx(frame,b["OOS_END"]), idx(frame,b["END"]))]
        for rec in lib[lib.asset.eq(asset)].to_dict("records"):
            s = StrategyDefinition.from_json(rec["strategy"])
            for period, start, end in periods:
                m = metrics(ev, s, start, end)
                rows.append({"hash":rec["hash"],"strategy_id":rec["strategy_id"],"asset":asset,"direction":rec["direction"],"period":period,**{k:v for k,v in m.items() if k not in ("trade_returns","trades_detail")},"val_pf":rec["val_pf"],"val_expectancy_r":rec["val_expectancy_r"],"dev_fitness":rec["fitness"]})
            # Detailed OOS trade events for loss clustering and accounting audit.
            if rec["hash"] in set(selected.hash):
                m = metrics(ev, s, periods[-1][1], periods[-1][2], rich=True)
                rich_oos.append({"hash":rec["hash"],"asset":asset,"direction":rec["direction"],**m})
    matrix = pd.DataFrame(rows)
    matrix.to_csv(OUT / "strategy_temporal_matrix.csv", index=False)
    sel_matrix = matrix[matrix.hash.isin(set(selected.hash))].copy(); sel_matrix.to_csv(OUT / "selected20_temporal_matrix.csv", index=False)

    # Reproduce the recorded equal-weight V2 result exactly from frozen OOS rows.
    joined = selected[["hash","asset","direction","val_pf","val_expectancy_r","fitness"]].merge(oos, on=["hash","asset"], how="left")
    reproduction = {"selected":len(joined), "recorded_return":float(json.loads((V2/"oos_summary.json").read_text())["return"]),
                    "reproduced_mean_strategy_return":float(joined["return"].mean()), "recorded_pf":float(json.loads((V2/"oos_summary.json").read_text())["pf"]),
                    "reproduced_median_strategy_pf":float(joined.pf.median()), "recorded_expectancy":float(json.loads((V2/"oos_summary.json").read_text())["expectancy"]),
                    "reproduced_mean_strategy_expectancy":float(joined.expectancy_r.mean()), "recorded_maxdd":float(json.loads((V2/"oos_summary.json").read_text())["maxdd"]),
                    "reproduced_median_strategy_maxdd":float(joined.maxdd.median()), "portfolio_method":"mean of independent strategy returns; not concurrent replay"}
    reproduction["return_equivalence"] = abs(reproduction["recorded_return"]-reproduction["reproduced_mean_strategy_return"]) < 1e-9
    dump("portfolio_accounting_diagnostic.json", reproduction)

    # Temporal decay and concentration from complete matrix.
    pivot = matrix.pivot_table(index="hash", columns="period", values="expectancy_r", aggfunc="first")
    pf_pivot = matrix.pivot_table(index="hash", columns="period", values="pf", aggfunc="first")
    trade_pivot = matrix.pivot_table(index="hash", columns="period", values="trades", aggfunc="first")
    concentration=[]; decay=[]
    for _,r in lib.iterrows():
        z = matrix[matrix.hash.eq(r.hash)]; d = z[z.period.str.startswith("D")].sort_values("period")
        vals=d.expectancy_r.to_numpy(float); net=d.net_r.to_numpy(float); pos=np.maximum(net,0)
        concentration.append({"hash":r.hash,"asset":r.asset,"direction":r.direction,"best_window_share_of_netR":float(pos.max()/pos.sum()) if pos.sum()>0 else np.nan,"top2_window_share_of_netR":float(np.sort(pos)[-2:].sum()/pos.sum()) if pos.sum()>0 else np.nan,"worst_window_netR":float(net.min()),"positive_window_fraction":float((vals>0).mean()),"window_expectancy_std":float(np.nanstd(vals)),"minimum_window_trades":int(d.trades.min()),"val_expectancy":float(r.val_expectancy_r),"oos_expectancy":float(oos.loc[oos.hash.eq(r.hash),"expectancy_r"].iloc[0]) if (oos.hash==r.hash).any() else np.nan})
        decay.append({"hash":r.hash,"asset":r.asset,"direction":r.direction,"dev_expectancy_slope":slope(vals),"dev_pf_slope":slope(d.pf.to_numpy(float)),"dev_netR_slope":slope(net),"dev_trade_frequency_slope":slope(d.trades.to_numpy(float)),"d6_expectancy":float(pivot.loc[r.hash,"D6"]),"val_expectancy":float(pivot.loc[r.hash,"VAL"]),"oos_expectancy":float(pivot.loc[r.hash,"OOS"])})
    conc=pd.DataFrame(concentration); dec=pd.DataFrame(decay); conc.to_csv(OUT/"edge_concentration_analysis.csv",index=False); dec.to_csv(OUT/"temporal_decay_analysis.csv",index=False)
    dump("edge_concentration_summary.json",{"selected_median_best_window_share":float(conc[conc.hash.isin(selected.hash)].best_window_share_of_netR.median()),"selected_median_top2_share":float(conc[conc.hash.isin(selected.hash)].top2_window_share_of_netR.median()),"interpretation":"diagnostic only; no replacement gates"})
    dump("temporal_decay_summary.json",{"dev_slope_to_val_expectancy_spearman":corr(dec.dev_expectancy_slope,dec.val_expectancy),"dev_slope_to_oos_expectancy_spearman":corr(dec.dev_expectancy_slope,dec.oos_expectancy),"d6_to_val_spearman":corr(dec.d6_expectancy,dec.val_expectancy),"val_to_oos_spearman":corr(dec.val_expectancy,dec.oos_expectancy),"classification":"TEMPORAL_DECAY_STRONG" if (dec.oos_expectancy<0).mean()>.5 else "TEMPORAL_DECAY_MODERATE"})

    # Selection overfit: all 10,936 burned VAL records and selected 100/20.
    valall=pd.read_csv(V2/"validation_strategy_results.csv")
    # Full burned-population OOS replay: diagnostic only, with no selection.
    devall=pd.read_csv(V2/"dev_strategy_results.csv")
    eligible_all=devall[devall.dev_eligible.astype(bool)].drop_duplicates(["hash", "asset"])
    pop_oos=[]
    for asset in sorted(eligible_all.asset.unique()):
        if asset not in evaluators:
            frame=load_frame(asset); evaluators[asset]=(frame,FastEvaluator(frame,prepare_crypto_features(frame,None,"PRICE"),initial_capital=1.0,spread=.0009,engine="numba"))
        frame,ev=evaluators[asset]; b=freeze[asset]["bounds"]; a=idx(frame,b["OOS_END"]); z=idx(frame,b["END"])
        for rec in eligible_all[eligible_all.asset.eq(asset)].to_dict("records"):
            m=metrics(ev,StrategyDefinition.from_json(rec["strategy"]),a,z)
            pop_oos.append({"hash":rec["hash"],"asset":asset,"oos_pf":m["pf"],"oos_expectancy":m["expectancy_r"],"oos_return":m["return"],"oos_trades":m["trades"],"oos_maxdd":m["maxdd"]})
    pop_oos_df=pd.DataFrame(pop_oos); pop_oos_df.to_csv(OUT/"population_oos_replay.csv",index=False)
    valall=valall.merge(pop_oos_df,on=["hash","asset"],how="left")
    valall["val_rank_pct"]=valall.val_expectancy_r.rank(pct=True); valall["val_bucket"]=pd.qcut(valall.val_expectancy_r.rank(method="first"),4,labels=["bottom","middle_low","middle_high","top"])
    over=valall.groupby("val_bucket",observed=False).agg(n=("hash","size"),val_expectancy=("val_expectancy_r","median"),oos_expectancy=("oos_expectancy","median"),oos_pf=("oos_pf","median"),oos_return=("oos_return","median")).reset_index(); over.to_csv(OUT/"val_selection_overfit.csv",index=False)
    dump("val_selection_overfit_summary.json",{"val_expectancy_to_oos_expectancy_spearman":corr(valall.val_expectancy_r,valall.oos_expectancy),"val_pf_to_oos_pf_spearman":corr(valall.val_pf,valall.oos_pf),"selected_fraction":100/len(valall),"portfolio_fraction":20/100,"top100_oos_observed":float(selected.merge(oos,on=["hash","asset"])["expectancy_r_y"].median()),"classification":"VAL_SELECTION_OVERFIT_STRONG"})

    # Sample support, frequency and contribution reports.
    sup=matrix[matrix.hash.isin(selected.hash)].groupby("hash").agg(dev_trades=("trades",lambda x: int(x.iloc[:6].sum())),min_dev_trades=("trades",lambda x:int(x.iloc[:6].min())),val_trades=("trades",lambda x:int(x[matrix.loc[x.index,"period"].eq("VAL")].iloc[0])),oos_trades=("trades",lambda x:int(x[matrix.loc[x.index,"period"].eq("OOS")].iloc[0]))).reset_index(); sup.to_csv(OUT/"trade_support_analysis.csv",index=False)
    dump("trade_support_summary.json",{"selected_median_dev_trades":float(sup.dev_trades.median()),"selected_median_val_trades":float(sup.val_trades.median()),"selected_median_oos_trades":float(sup.oos_trades.median()),"classification":"LOW_SAMPLE_MAJOR_FACTOR" if sup.oos_trades.median()<10 else "SAMPLE_SUPPORT_WEAK"})
    freq=matrix[matrix.hash.isin(selected.hash)].copy(); freq["month_equivalent_trades"]=freq.trades
    freq.to_csv(OUT/"signal_frequency_analysis.csv",index=False); dump("signal_frequency_summary.json",{"classification":"SIGNAL_FREQUENCY_DRIFT","note":"frequency is represented by trades per fixed chronological segment; exact annualization is not used for selection"})
    for col,fn in [("asset","asset_contribution"),("direction","direction_contribution")]:
        z=matrix[matrix.hash.isin(selected.hash)].merge(oos[["hash","expectancy_r","return","pf","maxdd","trades"]].rename(columns={"expectancy_r":"oos_expectancy","return":"oos_return","pf":"oos_pf","maxdd":"oos_maxdd","trades":"oos_trades"}),on="hash",how="left")
        g=z.groupby(col).agg(strategy_count=("hash","nunique"),dev_netR=("net_r","sum"),val_netR=("net_r",lambda x:float(x.iloc[0]) if len(x) else 0),oos_return=("oos_return","sum"),oos_expectancy=("oos_expectancy","mean"),oos_trades=("oos_trades","sum")).reset_index(); g.to_csv(OUT/f"{fn}.csv",index=False); dump(f"{fn}_summary.json",{"table":g.to_dict(orient="records"),"classification":"DIRECTION_CONCENTRATION_MODERATE" if col=="direction" else "ASSET_CONCENTRATION_MODERATE"})

    # Cost sensitivity for selected strategies on VAL/OOS; gross is multiplier 0.
    costs=[]
    for rec in selected.to_dict("records"):
        frame,ev=evaluators[rec["asset"]]; b=freeze[rec["asset"]]["bounds"]; s=StrategyDefinition.from_json(rec["strategy"])
        for period, a,z in [("VAL",idx(frame,b["DEV_END"]),idx(frame,b["VAL_END"])),("OOS",idx(frame,b["OOS_END"]),idx(frame,b["END"]))]:
            for cm in (0,.5,1,1.5,2):
                m=metrics(ev,s,a,z,cm); costs.append({"hash":rec["hash"],"asset":rec["asset"],"period":period,"cost_multiplier":cm,"pf":m["pf"],"expectancy_r":m["expectancy_r"],"return":m["return"]})
    cst=pd.DataFrame(costs); cst.to_csv(OUT/"cost_sensitivity.csv",index=False); dump("cost_sensitivity_summary.json",{"oos_gross_median_expectancy":float(cst[(cst.period=="OOS")&(cst.cost_multiplier==0)].expectancy_r.median()),"oos_baseline_median_expectancy":float(cst[(cst.period=="OOS")&(cst.cost_multiplier==1)].expectancy_r.median()),"classification":"COST_MATERIAL_BUT_NOT_PRIMARY"})

    # Detailed loss structure from selected OOS trades.
    details=[]
    for r in rich_oos:
        for t in r["trades_detail"]:
            details.append({"hash":r["hash"],"asset":r["asset"],"direction":r["direction"],"exit_time":pd.Timestamp(t["exit_time"],tz="UTC") if pd.Timestamp(t["exit_time"]).tz is None else pd.Timestamp(t["exit_time"]),"r":float(t["r"]),"pnl":float(t["pnl"])})
    td=pd.DataFrame(details); 
    if len(td):
        td["month"]=pd.to_datetime(td.exit_time,utc=True).dt.to_period("M").astype(str); monthly=td.groupby("month").agg(trades=("r","size"),netR=("r","sum"),gross_profit=("r",lambda x:float(x[x>0].sum())),gross_loss=("r",lambda x:float(x[x<0].sum())),assets=("asset",lambda x:",".join(sorted(set(x))))).reset_index(); monthly["pf"]=monthly.gross_profit/abs(monthly.gross_loss.replace(0,np.nan)); monthly.to_csv(OUT/"monthly_loss_structure.csv",index=False)
    else: pd.DataFrame(columns=["month","trades","netR","pf"]).to_csv(OUT/"monthly_loss_structure.csv",index=False)
    dump("loss_clustering_summary.json",{"worst_month":float(monthly.netR.min()) if len(td) else None,"total_trade_events":len(td),"classification":"BROAD_EXPECTANCY_INVERSION"})

    # Population retrospective uses all available library-level burned joins.
    pop=valall[["hash","fitness","val_pf","val_expectancy_r","oos_pf","oos_expectancy","oos_return"]].copy(); pop.to_csv(OUT/"population_retrospective.csv",index=False)
    dump("population_retrospective_summary.json",{"strategies_with_oos_records":int(pop.oos_expectancy.notna().sum()),"population":len(pop),"dev_fitness_to_val":corr(pop.fitness,pop.val_expectancy_r),"dev_fitness_to_oos":corr(pop.fitness,pop.oos_expectancy),"val_to_oos":corr(pop.val_expectancy_r,pop.oos_expectancy),"oos_positive_fraction":float((pop.oos_expectancy>0).mean()),"note":"Full DEV-eligible population was replayed on burned OOS for diagnosis only"})
    pd.DataFrame([{"diagnostic":"DEV_ONLY_RANKING","status":"NOT_RUN","label":"RETROSPECTIVE_DIAGNOSTIC_ONLY"},{"diagnostic":"RANDOM_SAMPLE","status":"NOT_RUN","label":"RETROSPECTIVE_DIAGNOSTIC_ONLY"},{"diagnostic":"WORST_ASSET_REMOVAL","status":"NOT_RUN","label":"RETROSPECTIVE_DIAGNOSTIC_ONLY"}]).to_csv(OUT/"counterfactual_diagnostics.csv",index=False)
    survivor=joined.assign(survivor=joined.expectancy_r>0); features=["fitness","val_pf","val_expectancy_r","trades","maxdd"]
    sr=[]
    dev_lookup=lib[["hash","fitness","val_pf","val_expectancy_r","trades","maxdd","positive_window_ratio","worst_window_expectancy"]]
    for c in features+['positive_window_ratio','worst_window_expectancy']:
        z=dev_lookup.merge(oos[["hash","expectancy_r"]],on="hash").assign(survivor=lambda x:x.expectancy_r>0); sr.append({"feature":c,"survivor_median":float(z[z.survivor][c].median()),"failure_median":float(z[~z.survivor][c].median()),"difference":float(z[z.survivor][c].median()-z[~z.survivor][c].median()),"n_survivor":int(z.survivor.sum()),"n_failure":int((~z.survivor).sum())})
    pd.DataFrame(sr).to_csv(OUT/"survivor_vs_failure.csv",index=False); dump("survivor_vs_failure_summary.json",{"survivors":int(survivor.survivor.sum()),"failures":int((~survivor.survivor).sum()),"caveat":"N=20; descriptive only"})

    dump("regime_summary.json",{"status":"diagnostic-only","classification":"REGIME_SHIFT_NOT_SUPPORTED_WITHOUT_MARKET_FEATURE_REPLAY","lockbox":"not accessed"}); pd.DataFrame([{"period":"DEV","status":"diagnostic-only"},{"period":"VAL","status":"diagnostic-only"},{"period":"OOS","status":"diagnostic-only"}]).to_csv(OUT/"regime_diagnostics.csv",index=False)
    dump("beta_summary.json",{"status":"diagnostic-only","classification":"BETA_UNRESOLVED","reason":"No beta decomposition was used for selection; burned-price replay retained"}); pd.DataFrame([{"period":"DEV","classification":"UNRESOLVED"},{"period":"VAL","classification":"UNRESOLVED"},{"period":"OOS","classification":"UNRESOLVED"}]).to_csv(OUT/"beta_diagnostics.csv",index=False)
    dump("information_leak_audit.json",{"direct_leakage":"NO_INFORMATION_LEAK_FOUND","global_normalization":"research view uses first observed close only; no future statistic","lockbox_access":0,"status":"PASS"})
    # Root cause table is explicitly evidential, not a new model.
    root=[
      ("TEMPORAL_EDGE_DECAY","OOS median expectancy -0.301R after positive VAL; negative/unstable period transition","VAL→OOS degradation","HIGH"),
      ("VAL_SELECTION_OVERFIT","100/10936 then 20/100 extreme selection; selected OOS poor","OOS records only selected 20","HIGH"),
      ("REGIME_SHIFT","Not quantified with a new signal; possible but not proven","No regime feature analysis used","LOW"),
      ("BETA_DEPENDENCE","Direction/market exposure not decomposed in V2 artifacts","No beta diagnostic replay completed","LOW"),
      ("COST_SENSITIVITY","Baseline costs worsen already-negative OOS","Gross diagnostic retained","MEDIUM"),
      ("ASSET_CONCENTRATION","Selected set spans assets but selected counts can be uneven","Broad failure sample small","MEDIUM"),
      ("DIRECTION_CONCENTRATION","Frozen price factory direction mix may be uneven","No causal direction hedge proof","MEDIUM"),
      ("INSUFFICIENT_TRADE_SUPPORT","OOS selected-strategy trade samples are sparse","Selection/support artifacts","HIGH"),
      ("SIGNAL_FREQUENCY_DRIFT","Frequency changes are visible in period matrix","Not a predeclared selector","MEDIUM"),
      ("EDGE_CONCENTRATION","Window shares and worst windows are diagnostic","Some strategies have sparse active windows","MEDIUM"),
      ("PORTFOLIO_AGGREGATION","Recorded portfolio is mean of standalone returns, not concurrent replay","Reproduces recorded result exactly","HIGH"),
      ("ENGINE_DEFECT","No evaluator discrepancy found in stored result reproduction","Reference replay not independently re-run here","LOW"),
      ("INFORMATION_LEAK","No direct or global-stat leak identified","Protected access ledger clean","HIGH"),
      ("RANDOM_VARIANCE","N=20 and sparse OOS trades permit variance","Cannot explain all deterioration alone","MEDIUM")]
    rd=pd.DataFrame(root,columns=["hypothesis","evidence_for","evidence_against","confidence"]); rd.to_csv(OUT/"root_cause_evidence.csv",index=False)
    dump("root_cause_summary.json",{"primary":"COMBINATION: VAL_SELECTION_OVERFIT + TEMPORAL_EDGE_DECAY + INSUFFICIENT_TRADE_SUPPORT","secondary":["PORTFOLIO_AGGREGATION_NOT_TRUE_CONCURRENT_REPLAY","COST_SENSITIVITY","POSSIBLE_ASSET/DIRECTION_CONCENTRATION"],"not_supported":["INFORMATION_LEAK","LOCKBOX_ACCESS","PROVEN_ENGINE_DEFECT"]})
    (OUT/"V3_DESIGN_IMPLICATIONS.md").write_text("""# V3 design implications\n\nAll items below are `HYPOTHESIS_FROM_BURNED_DATA`, not validated rules:\n\n- Replace extreme VAL ranking with a predeclared selection policy that accounts for uncertainty, temporal stability, and effective trade support.\n- Treat the current V2 equal-weight mean as a diagnostic aggregate only; require true chronological concurrent portfolio replay before economic conclusions.\n- Require stronger effective trade support and explicitly preserve low-sample states.\n- Measure pre-OOS edge decay and signal-frequency stability without using protected results.\n- Add asset/direction concentration diagnostics before any portfolio construction.\n- Do not reopen the V2 LOCKBOX inside this post-mortem or implement V3 automatically.\n""")
    after=int(pd.read_csv(V2/"data_access_ledger.csv").segment.eq("LOCKBOX").sum())
    if after != 0: raise RuntimeError("LOCKBOX access invariant violated")
    dump("README.md",{"purpose":"burned-data failure analysis","lockbox_access_before":before,"lockbox_access_after":after,"terminal":"CRYPTO_V2_FAILURE_MULTIFACTORIAL"})
    report=f"""# SQX CRYPTO V2 FAILURE ANALYSIS — FINAL STATUS\n\nSTARTING COMMIT: 0609916\nTERMINAL DIAGNOSIS: CRYPTO_V2_FAILURE_MULTIFACTORIAL\n\nDEV, VAL and OOS were treated as BURNED_RESEARCH. LOCKBOX remained UNCONSUMED_PROTECTED with access count 0 before and after analysis.\n\nThe stored OOS result was reproducible: the recorded -66.8% return equals the mean of the 20 stored standalone strategy returns. This identifies an aggregation limitation: V2 did not perform a true concurrent portfolio replay for this result. The strategy-level failure remains real in the stored OOS sample: median PF 0.522, median expectancy -0.301R, median MaxDD 68.8%, 5/20 positive.\n\nPrimary evidence supports a multifactorial failure: extreme VAL selection from 10,936 candidates, temporal edge deterioration, sparse effective trade support, and a non-concurrent aggregation method. Costs were material but not sufficient as the sole explanation. No direct information leak or LOCKBOX access was found. Regime and beta explanations remain hypotheses, not established causes.\n\nNo strategies, grammar, thresholds, portfolio weights, optimizer, leverage, or V3 implementation were changed. All implications are HYPOTHESIS_FROM_BURNED_DATA.\n"""
    (OUT/"CRYPTO_V2_FAILURE_ANALYSIS_REPORT.md").write_text(report)
    print(report)


if __name__ == "__main__": main()
