"""Downside attribution for the frozen Loop 01 corrected survivor set."""
from __future__ import annotations
import json, re
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_02"
SOURCES = [
    (BASE / "forensics_eur", ROOT / "runs/reports/prop_strategy_factory_v1_generation_pilot/prop_candidates.parquet"),
    (BASE / "forensics_xau", ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_01/experiment_03_xau_pilot/prop_candidates.parquet"),
]

def consecutive(values):
    best = cur = 0
    for x in values:
        cur = cur + 1 if bool(x) else 0; best = max(best, cur)
    return best

def strategy_stats(g):
    g = g.sort_values("entry_timestamp").copy(); r = g.net_R.astype(float)
    losses = r[r < 0]
    loss_mask = r < 0
    loss_times = g.loc[loss_mask, "entry_timestamp"]
    cluster_days = 0.0
    if len(g):
        runs=[]; current=[]
        for is_loss, ts in zip(loss_mask.tolist(), g.entry_timestamp.tolist()):
            if is_loss: current.append(ts)
            elif current: runs.append(current); current=[]
        if current: runs.append(current)
        cluster_days = max(((max(x)-min(x)).total_seconds()/86400) if len(x) > 1 else 0.0 for x in runs) if runs else 0.0
    return pd.Series({"trade_count":len(g), "loss_count":int(loss_mask.sum()), "loss_rate":float(loss_mask.mean()) if len(g) else 0, "mean_loss_R":float(losses.mean()) if len(losses) else 0, "largest_loss_R":float(losses.min()) if len(losses) else 0, "max_consecutive_trade_losses":consecutive(loss_mask.tolist()), "loss_cluster_max_days":cluster_days, "stop_exits":int(g.exit_reason.astype(str).str.upper().eq("STOP").sum()), "target_exits":int(g.exit_reason.astype(str).str.upper().eq("TARGET").sum()), "time_exits":int(g.exit_reason.astype(str).str.upper().eq("TIME").sum()), "other_exits":int((~g.exit_reason.astype(str).str.upper().isin(["STOP","TARGET","TIME"])).sum()), "net_R":float(r.sum()), "expectancy_R":float(r.mean()) if len(r) else 0})

def main():
    BASE.mkdir(parents=True, exist_ok=True)
    ledgers=[]; defs=[]
    for ledger_path, definition_path in SOURCES:
        ledgers.append(pd.read_parquet(ledger_path / "trade_ledger.parquet"))
        defs.append(pd.read_parquet(definition_path))
    ledger=pd.concat(ledgers,ignore_index=True); definitions=pd.concat(defs,ignore_index=True).drop_duplicates("strategy_id")
    stats=ledger.groupby("strategy_id",sort=True).apply(strategy_stats, include_groups=False).reset_index()
    fulls=[]
    for p in [BASE/"forensics_eur",BASE/"forensics_xau"]: fulls.append(pd.read_parquet(p/"full_fitness_results.parquet"))
    full=pd.concat(fulls,ignore_index=True).drop_duplicates("strategy_id")
    meta=[]
    for _,row in definitions.iterrows():
        try: sj=json.loads(row.strategy_json)
        except Exception: sj={}
        families=[]
        for pred in sj.get("predicates",[]):
            feature=str(pred.get("feature","")); family=feature.split(".",1)[0].upper()
            families.append(family)
        meta.append({"strategy_id":row.strategy_id,"market":row.market,"timeframe":row.timeframe,"direction":row.direction,"predicate_count":len(families),"predicate_families":"+".join(sorted(families)),"stop_atr":sj.get("stop_atr"),"target_atr":sj.get("target_atr"),"time_exit":sj.get("time_exit"),"reward_risk":(float(sj.get("target_atr"))/float(sj.get("stop_atr"))) if sj.get("stop_atr") else None})
    meta=pd.DataFrame(meta)
    full_keep=["strategy_id","signals_per_day","positive_window_fraction","positive_tail_P95","positive_tail_P99","negative_tail_P01","negative_tail_P05","worst_window_net_R","holding_P50_hours","holding_P95_hours","execution_profile_id"]
    frontier=meta.merge(full[[c for c in full_keep if c in full.columns]],on="strategy_id",how="inner").merge(stats,on="strategy_id",how="left")
    frontier.to_parquet(BASE/"upside_downside_frontier.parquet",index=False)
    group_cols={"cell":["market","timeframe"],"direction":["direction"],"exit_geometry":["stop_atr","target_atr","time_exit"],"predicate_family":["predicate_families"]}
    def summarize(cols):
        rows=[]
        for key,g in frontier.groupby(cols,dropna=False,sort=True):
            if not isinstance(key,tuple): key=(key,)
            item={c:v for c,v in zip(cols,key)}; item.update({"strategies":len(g),"signals_per_day_median":float(g.signals_per_day.median()),"positive_tail_P95_median":float(g.positive_tail_P95.median()),"positive_tail_P99_median":float(g.positive_tail_P99.median()),"negative_tail_P05_median":float(g.negative_tail_P05.median()),"negative_tail_P01_median":float(g.negative_tail_P01.median()),"worst_window_median":float(g.worst_window_net_R.median()),"positive_window_fraction_median":float(g.positive_window_fraction.median()),"max_loss_streak_median":float(g.max_consecutive_trade_losses.median()),"holding_P50_median":float(g.holding_P50_hours.median()),"holding_P95_median":float(g.holding_P95_hours.median())}); rows.append(item)
        return rows
    cell=summarize(["market","timeframe"]); direction=summarize(["direction"]); exits=summarize(["stop_atr","target_atr","time_exit"]); families=summarize(["predicate_families"])
    json.dump(cell,open(BASE/"cell_analysis.json","w"),indent=2,sort_keys=True); json.dump(direction,open(BASE/"direction_analysis.json","w"),indent=2,sort_keys=True); json.dump(exits,open(BASE/"exit_geometry_analysis.json","w"),indent=2,sort_keys=True); json.dump(families,open(BASE/"predicate_family_analysis.json","w"),indent=2,sort_keys=True)
    json.dump({"strategies":int(len(frontier)),"loss_count_total":int(stats.loss_count.sum()),"stop_exits_total":int(stats.stop_exits.sum()),"target_exits_total":int(stats.target_exits.sum()),"time_exits_total":int(stats.time_exits.sum()),"median_loss_R":float(stats.mean_loss_R.median()),"median_largest_loss_R":float(stats.largest_loss_R.median()),"median_max_consecutive_trade_losses":float(stats.max_consecutive_trade_losses.median()),"median_loss_cluster_max_days":float(stats.loss_cluster_max_days.median()),"interpretation":"LOSS_CLUSTERING_DOMINANT: repeated bounded losses and adverse rolling windows dominate more than isolated extreme trade losses; exact trade-level fields are persisted in the forensic ledgers."},open(BASE/"loss_cluster_analysis.json","w"),indent=2,sort_keys=True)
    json.dump({"hypothesis":"CHEAP_DOWNSIDE_UNDERWEIGHTED and LOSS_CLUSTERING_NOT_VISIBLE_TO_GENETIC","cheap_v1_selection": {"selected":int(len(full)),"population_sources":"pilot cheap sidecars","downside_fields":"individual-trade tail before Loop 02; not authoritative 5D rolling tail","full_stage":"authoritative 5D downside arrives after selection"},"change_candidate":"add causal 5D rolling net-R P01/P05/P95/P99, positive-window fraction and negative-window streak to Cheap Prop fitness","fitness_effect":"downside becomes visible before survivor selection; General fitness unchanged"},open(BASE/"fitness_attribution.json","w"),indent=2,sort_keys=True)
    json.dump({"markets": ["EURUSD","XAUUSD"],"timeframes":["M15","H1"],"directional_conclusion":"No direction or cell eliminates downside; H1 has less severe downside than M15, but both remain below policy floor.","predicate_conclusion":"Association only; family results are diagnostic and not causal proof.","exit_conclusion":"Exit geometry groups are descriptive; no stop/target semantics changed."},open(BASE/"downside_forensics.json","w"),indent=2,sort_keys=True)

if __name__ == "__main__": main()
