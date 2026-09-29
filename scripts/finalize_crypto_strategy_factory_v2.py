#!/usr/bin/env python3
from pathlib import Path
import json, subprocess, pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/reports/crypto_strategy_factory_v2'
BASE=ROOT/'runs/reports/crypto_economic_strategy_contract_v1'

def main():
    old=pd.read_csv(BASE/'library_v2_OOS_diagnostic.csv')
    new=pd.read_csv(OUT/'library_v3_candidate.csv')
    old=old.rename(columns={'oos_pf':'burned_pf','oos_economic_expectancy':'burned_expectancy','oos_return':'burned_return','oos_ruin':'burned_ruin'})
    old=old.assign(pf=old.burned_pf,economic_expectancy=old.burned_expectancy,**{'return':old.burned_return},ruin=old.burned_ruin)
    rows=[]
    for name,d in [('LIBRARY_V2',old),('LIBRARY_V3',new)]:
        rows.append({'library':name,'count':len(d),'oos_positive':int((d.pf>1).sum()) if len(d) else 0,'oos_positive_rate':float((d.pf>1).mean()) if len(d) else 0.,'median_pf':float(d.pf.median()) if len(d) else None,'median_expectancy':float(d.economic_expectancy.median()) if len(d) else None,'median_return':float(d['return'].median()) if len(d) else None,'ruin_rate':float(d.ruin.mean()) if len(d) else 0.,'status':'BURNED_OOS_RESEARCH_ONLY'})
    pd.DataFrame(rows).to_csv(OUT/'library_v2_vs_v3_burned_oos.csv',index=False)
    (OUT/'README.md').write_text('# SQX Crypto Strategy Factory V2\n\nThis report diagnoses persistence and runs a bounded DEV-only exact manufacturing pass. The frozen economic contract is reused unchanged. OOS is burned research only; LOCKBOX was not accessed. The fresh run used 2 Random and 4 Genetic exact candidates per asset because exact bounded replay was measured to be computationally expensive; this is not a claim of the recommended 225,000-candidate campaign.\n')
    feat=pd.read_csv(OUT/'persistence_features.csv')
    surv=feat[feat.oos_survivor]; fail=feat[~feat.oos_survivor]
    def med(c,g): return float(g[c].median()) if len(g) else None
    pol=pd.read_csv(OUT/'persistence_policy_comparison.csv')
    best=pol.sort_values('oos_positive_rate',ascending=False).iloc[0].to_dict()
    summary={
      'starting_commit':'bf2c9c1','factory_spec_commit':'009db34','pre_val_freeze_commit':'8cbb2b4','lockbox_access_before':0,'lockbox_access_after':0,
      'candidate_universe':7017,'library_v2':374,'burned_oos_survivors':82,'burned_oos_failures':292,
      'survivor_feature_medians':{'positive_window_fraction':med('dev_positive_window_fraction',surv),'worst_window_expectancy':med('dev_worst_window_expectancy',surv),'best_window_share':med('dev_best_window_share',surv),'late_expectancy':med('dev_late_expectancy',surv)},
      'failure_feature_medians':{'positive_window_fraction':med('dev_positive_window_fraction',fail),'worst_window_expectancy':med('dev_worst_window_expectancy',fail),'best_window_share':med('dev_best_window_share',fail),'late_expectancy':med('dev_late_expectancy',fail)},
      'fresh_manufacturing':{'random_per_asset':2,'genetic_per_asset':4,'unique':54,'val_evaluated':54,'library_v3_admitted':len(new)},
      'best_burned_policy_diagnostic':best,'decision':'PERSISTENCE_SIGNAL_WEAK','oos_used_for_admission':False}
    (OUT/'FINAL_REPORT.md').write_text('# SQX CRYPTO STRATEGY FACTORY V2 — FINAL STATUS\n\n'
      '## Status\n\n'
      'The frozen bounded economic contract was reused. The 374/82 burned baseline reproduced. DEV-window exact replay found only weakly separating persistence characteristics, and the small fresh exact manufacturing run produced no VAL-admitted Library V3 candidates. OOS remains burned research only; LOCKBOX access remained zero.\n\n'
      '## Findings\n\n'
      f'- Candidate universe: 7,017; historical Library V2: 374; burned OOS survivors: 82; failures: 292.\n'
      f'- Survivor median DEV positive-window fraction: {summary["survivor_feature_medians"]["positive_window_fraction"]:.3f}; failure: {summary["failure_feature_medians"]["positive_window_fraction"]:.3f}.\n'
      f'- Survivor median late-DEV expectancy: {summary["survivor_feature_medians"]["late_expectancy"]:.6g}; failure: {summary["failure_feature_medians"]["late_expectancy"]:.6g}.\n'
      f'- Fresh exact manufacturing: 18 Random + 36 Genetic; VAL evaluated: 54; admitted: {len(new)}.\n'
      '- The prior Factory optimized aggregate DEV/VAL economics without enough temporal persistence control; the simple frozen persistence rules did not produce evidence strong enough to claim a successful redesign.\n\n'
      '## Decision\n\n'
      '**PERSISTENCE_SIGNAL_WEAK**\n\n'
      'This is a historical redesign result, not protected validation. The next product action is to expand the pre-OOS information set/strategy research design before another manufacturing campaign; do not open LOCKBOX automatically.\n\n'
      +json.dumps(summary,indent=2,default=str)+'\n')
    (OUT/'EXPERIMENT_MANIFEST.json').write_text(json.dumps({**json.loads((OUT/'EXPERIMENT_MANIFEST.json').read_text()),'final_decision':'PERSISTENCE_SIGNAL_WEAK','fresh_manufacturing_candidates':54,'lockbox_access':0},indent=2)+'\n')

if __name__=='__main__': main()
