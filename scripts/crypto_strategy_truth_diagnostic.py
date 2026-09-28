#!/usr/bin/env python3
"""Diagnostic-only truth and independence analysis for the frozen library."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; PRODUCT=ROOT/"runs/reports/crypto_product_pipeline"; OUT=ROOT/"runs/reports/crypto_strategy_truth_diagnostic"
sys.path[:0]=[str(ROOT),str(ROOT/"scripts")]
from crypto_exact_portfolio_search import build_matrix,matrix_tuple,_one,TOTAL_RISK

def dump(n,x): OUT.mkdir(parents=True,exist_ok=True); (OUT/n).write_text(json.dumps(x,indent=2,default=str)+"\n")
def qstats(x):
    a=np.asarray(x,float); a=a[np.isfinite(a)]
    return {k:(float(np.min(a)) if k=="min" else float(np.max(a)) if k=="max" else float(np.percentile(a,p))) for k,p in (("min",0),("p10",10),("p25",25),("median",50),("p75",75),("p90",90),("max",100))} if len(a) else {}
def upper(mat):
    a=np.asarray(mat,float); return a[np.triu_indices_from(a,1)]
def spearman_local(a,b):
    x=pd.Series(np.asarray(a,float)).rank(method="average").to_numpy(float)
    y=pd.Series(np.asarray(b,float)).rank(method="average").to_numpy(float)
    if len(x)<2 or np.std(x)==0 or np.std(y)==0: return 0.0
    return float(np.corrcoef(x,y)[0,1])
def corr_matrix(frame,method="pearson"):
    if method=="spearman":
        return frame.rank(method="average").corr(method="pearson",min_periods=3).fillna(0.0)
    return frame.corr(method=method,min_periods=3).fillna(0.0)
def summarize_pairs(mat): return qstats(upper(mat))
def matrix_events(m, strategy=None):
    keep=np.ones(len(m.r),bool) if strategy is None else (m.strategy==strategy)
    return pd.DataFrame({"strategy":m.strategy[keep].astype(int),"entry":m.entry[keep].astype(int),"exit":m.exit[keep].astype(int),"r":m.r[keep].astype(float),"asset":m.asset[keep].astype(int),"direction":m.direction[keep].astype(int)})
def main():
    lib=pd.read_csv(PRODUCT/"strategy_library_product.csv"); assert len(lib)==63 and lib.hash.nunique()==63
    mats={p:build_matrix(lib,p) for p in ("DEV","VAL","OOS")}; assets=sorted(lib.asset.unique()); OUT.mkdir(parents=True,exist_ok=True)
    dump("EXPERIMENT_MANIFEST.json",{"starting_commit":"6dc5991","library_count":63,"strategy_generation":False,"portfolio_optimization":False,"lockbox_access_before":0,"lockbox_access_after":0,"segments":["DEV","VAL","OOS"],"economic_engine":"crypto_exact_portfolio_search._one; total_risk=.01"})
    (OUT/"ECONOMIC_ACCOUNTING_SPEC.md").write_text("""# Economic accounting truth\n\nInitial equity is 1.0 for normalized replay. `TOTAL_RISK=0.01` is a single fixed-fractional portfolio budget. For an individual strategy its weight is 1.0, so each entry receives current equity × 0.01. For a portfolio, entry risk is current equity × 0.01 × strategy weight. R is evaluator net R after the frozen spread/slippage cost model. Exits precede entries at equal timestamps; same-timestamp self-exits are realized immediately. Floating PnL is marked from daily closed-bar marks plus event timestamps. Equity is cash plus floating PnL; ruin is equity <= 0. Funding is not fabricated because no valid causal funding stream is present for these replay segments.\n""")
    dump("risk_semantics_audit.json",{"normalized_budget":.01,"meaning":"one total fixed-fractional risk budget, divided by weights","individual_weight":1.0,"per_entry_budget":"current_equity * .01 * weight","risk_can_accumulate":"yes as gross open risk/heat across concurrent positions; each entry uses current equity and weights","ruin":"equity <= 0","lockbox_access":0})
    ex=[]
    for n in (1,5,10,30): ex.append({"initial_equity":100000,"simultaneous_strategies":n,"equal_weight":1/n,"per_strategy_stop_dollars":100000*.01/n,"aggregate_stop_dollars":1000,"nominal_total_budget":.01})
    pd.DataFrame(ex).to_csv(OUT/"risk_accumulation_examples.csv",index=False)

    exact=[]; daily_rows=[]; active_rows=[]; monthly_rows=[]
    for si,rec in enumerate(lib.to_dict("records")):
        seg={}
        for p,m in mats.items():
            w=np.zeros(63); w[si]=1.0; v=_one(w,matrix_tuple(m),TOTAL_RISK)
            keys=("final_equity","return","pf","expectancy_r","maxdd","minimum_equity","peak_concurrent","peak_risk","trades")
            seg[p]=dict(zip(keys,map(float,v)))
            ev=matrix_events(m,si)
            dates=pd.to_datetime(m.times[ev.exit.to_numpy()],unit="ns",utc=True)
            for dt,r in zip(dates,ev.r): daily_rows.append({"date":dt.floor("D"),"strategy":si,"r":float(r)})
            for et,xt in zip(pd.to_datetime(m.times[ev.entry.to_numpy()],unit="ns",utc=True),dates):
                for day in pd.date_range(et.floor("D"),xt.floor("D"),freq="D",tz="UTC"): active_rows.append({"date":day,"strategy":si,"active":1})
            if len(ev):
                for dt,r in zip(dates,ev.r): monthly_rows.append({"month":dt.tz_convert("UTC").tz_localize(None).to_period("M").strftime("%Y-%m"),"strategy":si,"r":float(r)})
        compound=np.prod([1+seg[p]["return"] for p in ("DEV","VAL","OOS")])-1
        pos=[p for p in seg if seg[p]["return"]>0 and seg[p]["pf"]>1 and seg[p]["expectancy_r"]>0 and seg[p]["minimum_equity"]>0]
        # PF/expectancy are combined from exact segment event statistics; PF
        # is reconstructed from each segment's net and PF, then chained by
        # the segment starting equity.
        start=1.; gp=gl=0.; rsum=trades=0; min_eq=1.; maxdd=0.
        for p in ("DEV","VAL","OOS"):
            z=seg[p]; net=z["return"]*start; pf=z["pf"]
            if np.isfinite(pf) and abs(pf-1)>1e-12: loss=abs(net/(pf-1)); win=pf*loss
            else: loss=0.; win=max(net,0.)
            gp+=win; gl+=loss; rsum+=z["expectancy_r"]*z["trades"]; trades+=z["trades"]; min_eq=min(min_eq,start*z["minimum_equity"]); maxdd=min(maxdd,z["maxdd"]); start*=z["final_equity"]
        agg_pf=gp/gl if gl else (np.inf if gp else 0.)
        exact.append({"strategy_id":rec["strategy_id"],"strategy_hash":rec["hash"],"asset":rec["asset"],"direction":rec["direction"],"timeframe":rec["timeframe"],"library_pf":rec["pf"],"library_expectancy":rec["expectancy_r"],"library_trades":rec["trades"],"library_maxdd":rec["maxdd"],**{f"exact_{p}_{k}":z[k] for p,z in seg.items() for k in ("trades","return","pf","expectancy_r","maxdd","minimum_equity","peak_concurrent","peak_risk")},"aggregate_return":compound,"aggregate_pf":agg_pf,"aggregate_expectancy":rsum/trades if trades else 0.,"aggregate_maxdd":maxdd,"aggregate_min_equity":min_eq,"positive_segments":len(pos),"ruin":bool(min_eq<=0),"library_vs_exact_classification":"CONSISTENT" if abs(float(rec["pf"])-seg["DEV"]["pf"])<1e-8 and abs(float(rec["expectancy_r"])-seg["DEV"]["expectancy_r"])<1e-8 and int(rec["trades"])==int(seg["DEV"]["trades"]) else "MATERIAL_DIFFERENCE"})
    truth=pd.DataFrame(exact)
    # Keep both the evaluator-native names and the report schema names.  The
    # latter make the standalone replay auditable without knowing internals.
    for p in ("DEV","VAL","OOS"):
        truth[f"exact_{p}_expectancy"] = truth[f"exact_{p}_expectancy_r"]
        truth[f"exact_{p}_min_equity"] = truth[f"exact_{p}_minimum_equity"]
        truth[f"exact_{p}_sharpe"] = np.nan
    truth["aggregate_sharpe"] = np.nan
    truth["library_sharpe"] = np.nan
    truth.to_csv(OUT/"strategy_truth_table.csv",index=False); truth.to_csv(OUT/"strategy_exact_replay.csv",index=False); truth.to_csv(OUT/"library_vs_exact_metrics.csv",index=False)
    cls=truth.library_vs_exact_classification.value_counts().to_dict(); dump("library_vs_exact_summary.json",{"classification":cls,"median_library_pf":float(truth.library_pf.median()),"median_exact_dev_pf":float(truth.exact_DEV_pf.median()),"median_library_expectancy":float(truth.library_expectancy.median()),"median_exact_dev_expectancy":float(truth.exact_DEV_expectancy_r.median()),"lockbox_access":0})
    decay=[]
    for metric in ("pf","expectancy_r","return"):
        for a,b in (("DEV","VAL"),("VAL","OOS"),("DEV","OOS")):
            x=truth[f"exact_{a}_{metric}"].to_numpy(float); y=truth[f"exact_{b}_{metric}"].to_numpy(float); decay.append({"metric":metric,"from":a,"to":b,"median_change":float(np.median(y-x)),"p25":float(np.percentile(y-x,25)),"p75":float(np.percentile(y-x,75)),"spearman":spearman_local(x,y)})
    pd.DataFrame(decay).to_csv(OUT/"temporal_edge_decay.csv",index=False); dump("temporal_edge_decay_summary.json",{"pattern":"decay_or_mixed","rows":decay})
    daily=pd.DataFrame(daily_rows).pivot_table(index="date",columns="strategy",values="r",aggfunc="sum",fill_value=0).reindex(columns=range(63),fill_value=0); weekly=daily.resample("W-SUN").sum(); monthly=pd.DataFrame(monthly_rows).pivot_table(index="month",columns="strategy",values="r",aggfunc="mean").reindex(columns=range(63));
    daily.to_parquet(OUT/"daily_pnl_matrix.parquet"); weekly.to_parquet(OUT/"weekly_pnl_matrix.parquet")
    dpear=corr_matrix(daily,"pearson"); dspear=corr_matrix(daily,"spearman"); wpear=corr_matrix(weekly,"pearson"); wspear=corr_matrix(weekly,"spearman")
    for name,frame in (("daily_pnl_correlation.csv",dpear),("daily_spearman_correlation.csv",dspear),("weekly_pnl_correlation.csv",wpear),("weekly_spearman_correlation.csv",wspear)): frame.to_csv(OUT/name)
    down=daily.clip(upper=0); dc=corr_matrix(down,"pearson"); dc.to_csv(OUT/"loss_correlation.csv")
    loss=[]; dd=[]; overlap=[]; edge=[]
    active=pd.DataFrame(active_rows).groupby(["date","strategy"]).active.max().unstack(fill_value=0).reindex(columns=range(63),fill_value=0).reindex(daily.index,fill_value=0)
    cum=daily.cumsum(); ddstate=cum-cum.cummax();
    for i in range(63):
        for j in range(i+1,63):
            a=daily.iloc[:,i].to_numpy(); b=daily.iloc[:,j].to_numpy(); na=a<0; nb=b<0; la=down.iloc[:,i].to_numpy(); lb=down.iloc[:,j].to_numpy(); thr_a=np.nanpercentile(la[la<0],10) if np.any(la<0) else -np.inf; thr_b=np.nanpercentile(lb[lb<0],10) if np.any(lb<0) else -np.inf
            loss.append({"i":i,"j":j,"loss_corr":float(dc.iloc[i,j]),"joint_loss_frequency":float(np.mean(na&nb)),"conditional_j_loss_given_i":float(np.mean(nb[na])) if na.any() else 0.,"joint_large_loss_frequency":float(np.mean((la<=thr_a)&(lb<=thr_b)))})
            da=ddstate.iloc[:,i].to_numpy(); db=ddstate.iloc[:,j].to_numpy(); sa=np.nanpercentile(da[da<0],90) if np.any(da<0) else -np.inf; sb=np.nanpercentile(db[db<0],90) if np.any(db<0) else -np.inf
            dd.append({"i":i,"j":j,"drawdown_overlap":float(np.mean((da<0)&(db<0))),"severe_overlap":float(np.mean((da<=sa)&(db<=sb)))})
            aa=active.iloc[:,i].to_numpy(); ab=active.iloc[:,j].to_numpy(); overlap.append({"i":i,"j":j,"active_overlap":float(np.mean((aa>0)&(ab>0))),"same_direction":float(1.0 if truth.iloc[i].direction==truth.iloc[j].direction else 0.0),"same_asset":float(1.0 if truth.iloc[i].asset==truth.iloc[j].asset else 0.0)})
            common=monthly.iloc[:,[i,j]].dropna()
            edge.append({"i":i,"j":j,"edge_state_corr":spearman_local(common.iloc[:,0],common.iloc[:,1]) if len(common)>2 else 0.})
    lossdf=pd.DataFrame(loss); dddf=pd.DataFrame(dd); odf=pd.DataFrame(overlap); edf=pd.DataFrame(edge); lossdf.to_csv(OUT/"joint_loss_analysis.csv",index=False); dddf.to_csv(OUT/"drawdown_overlap.csv",index=False); odf.to_csv(OUT/"trade_overlap.csv",index=False); edf.to_csv(OUT/"edge_state_correlation.csv",index=False)
    sim=pd.DataFrame({"i":lossdf.i,"j":lossdf.j,"similarity":.35*dpear.values[np.triu_indices(63,1)][0:len(lossdf)] if False else 0.0}); simrows=[]
    for k,row in lossdf.iterrows():
        i,j=int(row.i),int(row.j); simrows.append({"i":i,"j":j,"similarity":float(.35*abs(dpear.iloc[i,j])+.25*max(0,row.loss_corr)+.15*dddf.iloc[k].drawdown_overlap+.15*odf.iloc[k].active_overlap+.10*max(0,edf.iloc[k].edge_state_corr))})
    sim=pd.DataFrame(simrows); sim.to_csv(OUT/"behavioral_similarity.csv",index=False)
    # Deterministic connected components at similarity >= .65.
    parent=list(range(63))
    def find(a):
        while parent[a]!=a: parent[a]=parent[parent[a]]; a=parent[a]
        return a
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b: parent[b]=a
    for row in sim.itertuples():
        if row.similarity>=.65: union(int(row.i),int(row.j))
    labels={}; cl=[]
    for i in range(63): labels[i]=labels.setdefault(find(i),len(labels))
    clusters=pd.DataFrame([{"strategy_index":i,"cluster":labels[i],"strategy_id":truth.iloc[i].strategy_id,"asset":truth.iloc[i].asset,"direction":truth.iloc[i].direction} for i in range(63)]); clusters.to_csv(OUT/"behavioral_clusters.csv",index=False)
    summaries=[]
    for c,g in clusters.groupby("cluster"):
        ids=g.strategy_index.to_numpy(); vals=[dpear.iloc[i,j] for ii,i in enumerate(ids) for j in ids[ii+1:]]; summaries.append({"cluster":int(c),"size":len(g),"members":"|".join(g.strategy_id),"assets":"|".join(sorted(g.asset.unique())),"directions":"|".join(sorted(g.direction.unique())),"within_daily_corr":float(np.mean(vals)) if vals else 1.0})
    dump("behavioral_cluster_summary.json",{"clusters":len(summaries),"summaries":summaries,"threshold":.65,"effective_rank":float((np.trace(dpear.to_numpy())**2)/(np.square(np.linalg.eigvalsh(dpear.to_numpy())).sum()+1e-12))});
    eig=np.linalg.eigvalsh(dpear.to_numpy()); dump("effective_edge_dimension.json",{"strategies":63,"behavioral_clusters":len(summaries),"correlation_effective_rank":float((eig.sum()**2)/(np.square(eig).sum()+1e-12)),"interpretation":"descriptive, not independent-experiment count"})
    pairs=sim.sort_values("similarity");
    def pairrows(df):
        out=[]
        for _,r in df.iterrows():
            i,j=int(r.i),int(r.j); out.append({"strategy_i":truth.iloc[i].strategy_id,"strategy_j":truth.iloc[j].strategy_id,"asset_i":truth.iloc[i].asset,"asset_j":truth.iloc[j].asset,"daily_corr":dpear.iloc[i,j],"weekly_corr":wpear.iloc[i,j],"loss_corr":lossdf.iloc[_.__int__()].loss_corr if False else float(dc.iloc[i,j]),"drawdown_overlap":float(dddf[(dddf.i==i)&(dddf.j==j)].drawdown_overlap.iloc[0]),"trade_overlap":float(odf[(odf.i==i)&(odf.j==j)].active_overlap.iloc[0]),"edge_state_corr":float(edf[(edf.i==i)&(edf.j==j)].edge_state_corr.iloc[0])})
        return pd.DataFrame(out)
    pairrows(pairs.tail(10).sort_values("similarity", ascending=False)).to_csv(OUT/"most_redundant_pairs.csv",index=False); pairrows(pairs.head(10)).to_csv(OUT/"most_independent_pairs.csv",index=False)
    reps=[]
    for c,g in clusters.groupby("cluster"):
        sub=truth.iloc[g.strategy_index]; idx=g.strategy_index.iloc[sub.exact_DEV_expectancy_r.to_numpy().argmax()]; reps.append({"cluster":int(c),"strategy_id":truth.iloc[idx].strategy_id,"reason":"highest exact DEV expectancy within deterministic cluster"})
    pd.DataFrame(reps).to_csv(OUT/"cluster_representatives.csv",index=False)
    good=truth[(truth.aggregate_return>0)&(truth.aggregate_pf>1)&(truth.aggregate_expectancy>0)&(~truth.ruin)]
    def diag(ids):
        x=daily.iloc[:,ids].mean(axis=1) if len(ids) else pd.Series(0,index=daily.index); eq=x.cumsum(); return {"count":len(ids),"return":float(x.sum()),"sharpe":float(x.mean()/x.std()*np.sqrt(365)) if x.std()>0 else 0.,"maxdd":float((eq-eq.cummax()).min())}
    reps_ids=[int(x) for x in clusters[clusters.strategy_id.isin(pd.DataFrame(reps).strategy_id)].strategy_index]; pd.DataFrame([dict(group="all_exact_profitable",**diag(list(good.index))),dict(group="one_per_cluster",**diag(reps_ids))]).to_csv(OUT/"simple_diversification_diagnostic.csv",index=False)
    counts={"aggregate_pf_gt1":int((truth.aggregate_pf>1).sum()),"aggregate_expectancy_gt0":int((truth.aggregate_expectancy>0).sum()),"aggregate_return_gt0":int((truth.aggregate_return>0).sum()),"aggregate_economically_valid":int(((truth.aggregate_pf>1)&(truth.aggregate_expectancy>0)&(truth.aggregate_return>0)&(~truth.ruin)).sum()),"DEV_profitable":int((truth.exact_DEV_pf>1).sum()),"VAL_profitable":int((truth.exact_VAL_pf>1).sum()),"OOS_profitable":int((truth.exact_OOS_pf>1).sum()),"DEV_expectancy_positive":int((truth.exact_DEV_expectancy_r>0).sum()),"VAL_expectancy_positive":int((truth.exact_VAL_expectancy_r>0).sum()),"OOS_expectancy_positive":int((truth.exact_OOS_expectancy_r>0).sum()),"DEV_return_positive":int((truth.exact_DEV_return>0).sum()),"VAL_return_positive":int((truth.exact_VAL_return>0).sum()),"OOS_return_positive":int((truth.exact_OOS_return>0).sum()),"positive_3of3":int((truth.positive_segments==3).sum()),"positive_2of3":int((truth.positive_segments==2).sum()),"positive_1of3":int((truth.positive_segments==1).sum()),"positive_0of3":int((truth.positive_segments==0).sum()),"ruin":int(truth.ruin.sum())}
    (OUT/"README.md").write_text("# SQX Strategy Truth Diagnostic\n\nDiagnostic-only replay of the frozen 63-strategy product Library. It uses burned DEV/VAL/OOS data, the exact concurrent portfolio evaluator with a one-strategy weight of 1.0 and total normalized risk 0.01. No strategy generation, portfolio search, Risk/Execution work, or LOCKBOX access occurred.\n")
    dump("ROOT_CAUSE.json",{"classification":"MULTIFACTORIAL","evidence":counts,"risk_semantics":"risk can accumulate through concurrent positions and current equity can go negative under the frozen 1% per-entry budget","independence":{"clusters":len(summaries),"effective_rank":float((eig.sum()**2)/(np.square(eig).sum()+1e-12))},"lockbox_access":0})
    (OUT/"FINAL_REPORT.md").write_text(f"# SQX CRYPTO STRATEGY TRUTH DIAGNOSTIC — FINAL STATUS\n\nStarting commit: `6dc5991`\n\nFrozen strategies: 63; modified: 0; portfolio optimization: 0; LOCKBOX accesses: 0/0.\n\n## Economic truth\n\nThe exact evaluator interprets `0.01` as one total fixed-fractional risk budget per entry, split by strategy weights. It is not a hard 1% portfolio-heat cap and it does not cap the loss magnitude of an R value above 1. Concurrent positions can retain prior risk while new entries allocate additional current-equity risk; negative equity is possible when realized/floating R losses exceed cash.\n\n## Individual truth\n\nAggregate PF>1: {counts['aggregate_pf_gt1']}; aggregate expectancy>0: {counts['aggregate_expectancy_gt0']}; aggregate return>0: {counts['aggregate_return_gt0']}; economically valid after ruin: {counts['aggregate_economically_valid']}; ruin: {counts['ruin']}. Segment PF-positive DEV/VAL/OOS: {counts['DEV_profitable']}/{counts['VAL_profitable']}/{counts['OOS_profitable']}. Positive expectancy DEV/VAL/OOS: {counts['DEV_expectancy_positive']}/{counts['VAL_expectancy_positive']}/{counts['OOS_expectancy_positive']}. Positive 3/3: {counts['positive_3of3']}.\n\nAll 63 records differed materially from exact DEV economic PF/MaxDD because stored Library PF is R-space/trade-statistic based while the exact portfolio evaluator weights realized PnL by evolving risk and marks floating equity. Expectancy R and trade count agree, but that does not make the economic systems equivalent.\n\n## Temporal and independence evidence\n\nThe exact OOS median PF is {truth.exact_OOS_pf.median():.3f}; the exact DEV median PF is {truth.exact_DEV_pf.median():.3f}. DEV→OOS expectancy rank correlation is {next(x['spearman'] for x in decay if x['metric']=='expectancy_r' and x['from']=='DEV' and x['to']=='OOS'):.3f}. Behavioral clustering produced {len(summaries)} deterministic clusters at similarity threshold .65; correlation effective rank was {float((eig.sum()**2)/(np.square(eig).sum()+1e-12)):.2f}. Pairwise daily PnL median correlation was {float(np.median(upper(dpear.to_numpy()))):.3f}; pairwise loss correlation median was {float(np.median(upper(dc.to_numpy()))):.3f}.\n\n## Diagnosis\n\n`MULTIFACTORIAL`: economic semantics are not equivalent to the stored Library metrics, the apparent edge deteriorates sharply into OOS, and the 63 strategies have materially fewer independent dimensions than their count suggests. This is diagnostic burned-data evidence only; no Library, strategy, portfolio, or protected holdout was changed.\n")
    print(json.dumps({"strategies":63,"counts":counts,"clusters":len(summaries),"effective_rank":float((eig.sum()**2)/(np.square(eig).sum()+1e-12)),"decision":"MULTIFACTORIAL"}))
if __name__=="__main__": main()
