from pathlib import Path
import json, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_clean_reboot_v1'
def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+'\n')
def main():
    (OUT/'PROFIT_FIRST_FITNESS_SPEC.md').write_text('# Profit-first fitness\n\nThe frozen design would prioritize exact economic expectancy, net return, compounded growth and PF, with secondary temporal support and profit concentration penalties. Hard invalidity: ruin, invalid replay, insufficient trades, or unbounded heat. Manufacturing is DEV-only. This specification was not used for a large search because the exact benchmark projected approximately 144 hours for 250,000 candidates.\n')
    dump('ECONOMIC_CONTRACT.json',{'source':'runs/reports/crypto_economic_strategy_contract_v1/STRATEGY_ECONOMIC_CONTRACT.md','risk_fraction':0.01,'maximum_standalone_heat':0.01,'compounding':'current equity fixed fractional','funding':'FUNDING_NOT_MODELED','lockbox_access':0})
    empty={'strategy_id':pd.Series(dtype=str),'hash':pd.Series(dtype=str),'direction':pd.Series(dtype=str),'kind':pd.Series(dtype=str),'status':pd.Series(dtype=str)}
    for n in ['random_candidates.parquet','genetic_candidates.parquet','profit_concentration.parquet','behavioral_fingerprints.parquet','val_results.parquet','library_v1.parquet','oos_results.parquet']:
        pd.DataFrame(empty).to_parquet(OUT/n,index=False)
    pd.DataFrame([{'stage':'manufacturing','requested_random':50000,'requested_genetic':200000,'evaluated':0,'status':'BLOCKED_ON_COMPUTE','projected_hours':144.0},{'stage':'VAL','status':'NOT_REACHED'},{'stage':'OOS','status':'NOT_ACCESSED'}]).to_csv(OUT/'dev_candidate_funnel.csv',index=False)
    dump('library_v1_summary.json',{'status':'NOT_REACHED','reason':'BLOCKED_ON_COMPUTE','strategies':0,'lockbox_access':0})
    dump('factory_generalization.json',{'status':'NOT_REACHED','oos_accessed':False,'reason':'manufacturing not completed'})
    dump('portfolio_readiness.json',{'assessment':'PORTFOLIO_RAW_MATERIAL_INSUFFICIENT','status':'NOT_REACHED','reason':'no Library manufactured; Portfolio Factory closed'})
    dump('PRE_VAL_FREEZE.json',{'status':'NOT_REACHED_BLOCKED_ON_COMPUTE','manufacturing_evaluations':0,'val_accessed':False,'oos_accessed':False,'lockbox_access':0})
    dump('PRE_OOS_FREEZE.json',{'status':'NOT_REACHED','oos_accessed':False,'lockbox_access':0})
    (OUT/'FINAL_REPORT.md').write_text('''# SQX CRYPTO CLEAN REBOOT V1 — FINAL STATUS\n\n## Decision\n\n**BLOCKED_ON_COMPUTE**\n\nThe long BTCUSDT M15 source was accepted for signal research. The canonical bounded fast/reference equivalence benchmark passed 100/100 with zero maximum metric delta, but exact six-window evaluation throughput was 0.482 strategies/sec, projecting approximately 144 hours for the required 250,000 candidates. No large search was launched or silently reduced.\n\nThe OOS segment and LOCKBOX were not accessed. LOCKBOX access remained zero. Portfolio Factory, Risk Engine, and Execution Engine were not opened.\n\n## Next action\n\nImplement a batched/multiprocess exact signal-and-economic evaluator, then rerun the frozen benchmark before manufacturing.\n''')
if __name__=='__main__': main()
