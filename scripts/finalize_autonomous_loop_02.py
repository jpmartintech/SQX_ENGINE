"""Persist the bounded Loop 02 decision and experiment artifacts."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/"runs/reports/prop_strategy_factory_v1_autonomous_loop_02"

def dump(name,value): (BASE/name).write_text(json.dumps(value,indent=2,sort_keys=True,default=str)+"\n")
def stats(path):
    d=pd.concat([pd.read_parquet(path/"full_fitness_results.parquet")],ignore_index=True)
    return {k:float(d[k].median()) for k in ["signals_per_day","positive_window_fraction","positive_tail_P95","positive_tail_P99","negative_tail_P01","negative_tail_P05","worst_window_net_R","holding_P50_hours","holding_P95_hours"]}
def stage(path):
    d=pd.read_parquet(path/"funnel_results.parquet")
    return {s:{st:int(n) for st,n in g.status.value_counts().items()} for s,g in d.groupby("stage")}
def main():
    iteration_paths={"1":BASE/"iteration_1_retry","2":BASE/"iteration_2","3":BASE/"iteration_3"}
    baseline={"signals_per_day":2.7584627638391077,"positive_window_fraction":.48286169788760464,"positive_tail_P95":6.888849414291226,"positive_tail_P99":9.079348608537048,"negative_tail_P01":-8.142806076880442,"negative_tail_P05":-5.708697411962241,"worst_window_net_R":-13.053027402822437,"holding_P50_hours":2.0,"holding_P95_hours":4.0}
    results={k:stats(p) for k,p in iteration_paths.items()}
    for k,p in iteration_paths.items():
        results[k]["stage_counts"]=stage(p); results[k]["seed"]={"1":4102,"2":4103,"3":4104}[k]; results[k]["generated"]=2000; results[k]["candidates"]=0; results[k]["oos_accesses"]=0
    dump("iteration_1.json",{"hypothesis":"CHEAP_DOWNSIDE_UNDERWEIGHTED / LOSS_CLUSTERING_NOT_VISIBLE","change":"causal 5D rolling downside and loss-streak descriptors in Cheap fitness","version":"PROP_FITNESS_V2_DOWNSIDE","result":results["1"],"classification":"NO_MATERIAL_CHANGE"})
    dump("iteration_2.json",{"hypothesis":"wider stop geometry reduces repeated stop-loss clustering","change":"stop_atr={1.5,2.0}; wider-stop exit version","version":"PROP_EXIT_V2_WIDER_STOP","result":results["2"],"classification":"MATERIAL_DOWNSIDE_IMPROVEMENT_BUT_GATE_FAIL"})
    dump("iteration_3.json",{"hypothesis":"remove fragile high-target/short-time combinations","change":"target_atr={1.0,1.5,2.0}; time_exit={8,12,24}; wider stops retained","version":"PROP_EXIT_V3_STABLE_EXIT","result":results["3"],"classification":"NO_ADDITIONAL_MATERIAL_IMPROVEMENT"})
    dump("phase_d_results.json",{"executed":False,"reason":"zero legitimate pre-Phase-D candidates"}); dump("phase_e_results.json",{"executed":False,"reason":"Phase D entry condition not met"}); dump("ab_results.json",{"executed":False,"reason":"no PROP_READY strategies"})
    dump("performance.json",{"forensic_replay_seconds":1028.3758760890046,"iteration_seconds":{"1":530.2609558710101,"2":546.7977922249993,"3":525.9326949730021},"total_bounded_seconds":2631.366,"estimated_10k_seconds":{"1":2651.3,"2":2734.0,"3":2629.7},"oos_accesses":0,"peak_rss_mib_max":4545.0})
    dump("autonomous_loop_02_summary.json",{"starting_commit":"d4aa732e6a1b2721ee2d4a15fe92265bf7915347","iterations_executed":3,"generated_per_iteration":2000,"total_generated":6000,"candidates":0,"baseline":baseline,"iterations":results,"final_classification":"PROP_FACTORY_DOWNSIDE_TOO_HIGH","phase_d":False,"phase_e":False,"ab":False,"oos_accesses":0,"general_factory_modified":False,"mql5_modified":False})
    ledger=[
      {"experiment_id":"01_forensics","parent":None,"hypothesis":"identify source of clustered 5D downside","commit":"d4aa732","fitness_version":"PROP_FITNESS_V1","grammar_version":"PROP_GRAMMAR_V1","exit_version":"PROP_EXIT_V1","policy_version":"PROP_POLICY_VERSION_1","markets":["EURUSD","XAUUSD"],"timeframes":["M15","H1"],"seed":4101,"strategy_count":1199,"oos_accesses":0,"result":"LOSS_CLUSTERING_DOMINANT; individual losses near -1R; long consecutive loss runs","decision":"add causal 5D downside to Cheap fitness"},
      {"experiment_id":"02_iteration_1","parent":"01_forensics","hypothesis":"Cheap fitness is insufficiently downside-aware","commit":"PENDING","fitness_version":"PROP_FITNESS_V2_DOWNSIDE","grammar_version":"PROP_GRAMMAR_V1","exit_version":"PROP_EXIT_V1","policy_version":"PROP_POLICY_VERSION_1","markets":["EURUSD","XAUUSD"],"timeframes":["M15","H1"],"seed":4102,"strategy_count":2000,"oos_accesses":0,"result":"no material downside improvement; zero candidates","decision":"exit geometry hypothesis"},
      {"experiment_id":"03_iteration_2","parent":"02_iteration_1","hypothesis":"wider stops reduce repeated stop-loss clusters","commit":"PENDING","fitness_version":"PROP_FITNESS_V2_DOWNSIDE","grammar_version":"PROP_GRAMMAR_V1","exit_version":"PROP_EXIT_V2_WIDER_STOP","policy_version":"PROP_POLICY_VERSION_1","markets":["EURUSD","XAUUSD"],"timeframes":["M15","H1"],"seed":4103,"strategy_count":2000,"oos_accesses":0,"result":"P05 improved to approximately -5.01R; upside declined; zero candidates","decision":"stable-exit refinement"},
      {"experiment_id":"04_iteration_3","parent":"03_iteration_2","hypothesis":"high targets and short time exits contribute to fragility","commit":"PENDING","fitness_version":"PROP_FITNESS_V2_DOWNSIDE","grammar_version":"PROP_GRAMMAR_V1","exit_version":"PROP_EXIT_V3_STABLE_EXIT","policy_version":"PROP_POLICY_VERSION_1","markets":["EURUSD","XAUUSD"],"timeframes":["M15","H1"],"seed":4104,"strategy_count":2000,"oos_accesses":0,"result":"no additional material improvement; zero candidates","decision":"stop after three manufacturing iterations"}
    ]
    (BASE/"experiment_ledger.json").write_text("\n".join(json.dumps(x,sort_keys=True) for x in ledger)+"\n")
    (BASE/"factory_readiness_report.md").write_text("# PROP STRATEGY FACTORY V1 — AUTONOMOUS LOOP 02\n\nThree bounded Prop-specific manufacturing iterations were completed. Cheap downside visibility and exit-range changes did not produce legitimate PROP_CANDIDATE strategies. The final evidence remains downside-limited; Phase D and Phase E were not entered.\n")
    hashes={str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in BASE.rglob("*") if p.is_file() and p.name!="artifact_hashes.json"}; dump("artifact_hashes.json",hashes)
if __name__=="__main__": main()
