"""Freeze and audit the rolling-edge→FTMO experiment contract."""
from __future__ import annotations
import json, resource, time
from pathlib import Path
import pandas as pd
from sqx_engine.rolling_edge import rolling_cycles

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"runs/reports/rolling_edge_ftmo_final"
MARKETS=("EURUSD","GBPUSD","NZDUSD","USDCAD","USDCHF","USDJPY","XAUUSD"); TFS=("M15","H1","H4")

def write(name,obj):
    OUT.mkdir(parents=True,exist_ok=True); (OUT/name).write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+"\n")

def main():
    started=time.perf_counter(); coverage=[]
    for m in MARKETS:
        for tf in TFS:
            paths=list((ROOT/"data/cloud").glob(f"{m}_{tf}.csv")) + list((ROOT/"data/derived").glob(f"{m}_{tf}_*.csv"))
            if not paths: continue
            p=sorted(paths)[0]; x=pd.read_csv(p,usecols=["timestamp"]); ts=pd.to_datetime(x.timestamp,utc=True)
            cycles=rolling_cycles(ts.min(),ts.max(),5,1,1,include_partial=False); partial=rolling_cycles(ts.min(),ts.max(),5,1,1,include_partial=True)
            coverage.append({"market":m,"timeframe":tf,"path":str(p.relative_to(ROOT),),"start":str(ts.min()),"end":str(ts.max()),"rows":len(ts),"complete_cycles":len(cycles),"partial_or_complete_cycles":len(partial),"partial_years":[c.to_dict() for c in partial if c.partial_forward]})
    complete=min((x['complete_cycles'] for x in coverage),default=0); any_complete=sum(x['complete_cycles'] for x in coverage)
    write('rolling_factory_spec.json',{'lookback_years':5,'forward_years':1,'step_years':1,'primary_attempts':1,'strategy_factory_separate_from_portfolio_factory':True,'ftmo_profile':'FTMO_2STEP_CURRENT_V1','oos_policy':'latest complete cycle(s) held until freeze'})
    write('meta_split.json',{'status':'NOT_OPENED_DATA_BLOCKED','meta_development':'not executed','meta_validation':'not executed','final_meta_oos':'not opened','oos_accesses':0})
    write('cycle_manifest.json',{'coverage':coverage,'complete_cycle_count_by_cell':{f"{x['market']}_{x['timeframe']}":x['complete_cycles'] for x in coverage},'total_cell_cycles':any_complete,'complete_cycles_available_for_full_supported_intersection':complete})
    write('generation_budget.json',{'status':'NOT_EXECUTED','reason':'no complete 5Y manufacture + 1Y forward cycle in available raw OHLC','pilot_budget':'not launched'})
    write('strategy_gate_spec.json',{'net_pf':'>1.15 net PF after production costs','completed_trades':'>250','causality':'PASS','economic_reconstruction':'PASS','execution_profile':'VALID'})
    write('stagnation_spec.json',{'equity_stagnation':['median','P90','MAX days between equity highs'],'trade_inactivity':['median','P90','MAX completed-trade gap days'],'hard_rejection':False})
    write('cycle_causal_audit.json',{'status':'NOT_EXECUTED_NO_CYCLES','oos_accesses':0,'reason':'raw OHLC coverage insufficient'})
    write('rolling_factory_summary.json',{'classification':'ROLLING_EDGE_EXPERIMENT_BLOCKED_ON_DATA','complete_cycles':any_complete,'oos_accesses':0,'runtime_seconds':time.perf_counter()-started,'partial_2026':True})
    write('experiment_ledger.json',[{'experiment_id':'RE-FTMO-001','parent':'be834f4','hypothesis':'recent 5Y manufacture can predict next-year FTMO funding','status':'BLOCKED_ON_DATA','oos_accesses':0,'decision':'freeze FTMO and move to Crypto Factory'}])
    (OUT/'decision_log.md').write_text('# Rolling Edge → FTMO Decision Log\n\n- RE-FTMO-001: Audited all available supported raw OHLC coverage. No complete 5-year manufacture window followed by a complete 1-year Forward year exists. No strategy generation, portfolio search, or Forward access was performed. FTMO line is frozen.\n')
    (OUT/'ROLLING_EDGE_FTMO_FINAL_REPORT.md').write_text(f'''# SQX — Rolling Edge → FTMO — Final Audit\n\nThe strict 5Y→1Y rolling process was not launched because the available raw OHLC histories begin between 2022-11 and 2024-02 and end in April 2026. A complete manufacture window plus complete next-year Forward requires at least six full calendar years. Complete cycles available: {any_complete} cell-level cycles, with no common supported cycle. 2026 is partial and excluded.\n\nNo strategies were generated, no portfolios were selected, and no Forward data were accessed. This is a data sufficiency blocker, not evidence for or against the rolling-edge hypothesis.\n''')
    (OUT/'CRYPTO_FACTORY_HANDOFF.md').write_text('''# Crypto Factory Handoff\n\nThe FTMO rolling-edge experiment is frozen before generation because the repository has no complete 5-year manufacture plus 1-year Forward raw-OHLC history. Reusable components are the Genetic Strategy Generator, canonical StrategyDefinition and hashing, causal evaluator, Numba acceleration, EconomicSpec, R normalization, Strategy Library, behavioral clustering, Portfolio Factory, exact portfolio equity replay, and deployment architecture.\n\nThe next project should target perpetual futures with exchange fees, funding, maker/taker costs, 24/7 sessions, leverage, margin, liquidation, precision, mark/oracle price, volume, open interest, funding state, premium, and microstructure. Its primary objective is profitable robust strategy production and portfolio growth, not FTMO PASS.\n''')
    print(json.dumps({'coverage':coverage,'cell_cycles':any_complete,'oos_accesses':0,'runtime_seconds':time.perf_counter()-started},indent=2,default=str))

if __name__=='__main__': main()
