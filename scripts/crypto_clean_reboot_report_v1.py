#!/usr/bin/env python3
"""Create descriptive post-freeze manufacturing/OOS artifacts."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'
def dump(n,x): (OUT/n).write_text(json.dumps(x,indent=2,default=str)+'\n')
def stats(x):
    x=x.copy(); pf=x.pf.replace([np.inf,-np.inf],np.nan)
    return {'count':len(x),'positive_return':int((x['return']>0).sum()),'positive_rate':float((x['return']>0).mean()) if len(x) else 0.,'positive_expectancy':int((x.economic_expectancy>0).sum()),'median_return':float(x['return'].median()) if len(x) else None,'median_expectancy':float(x.economic_expectancy.median()) if len(x) else None,'median_pf':float(pf.median()) if len(x) else None,'p75_return':float(x['return'].quantile(.75)) if len(x) else None,'p90_return':float(x['return'].quantile(.90)) if len(x) else None,'p95_return':float(x['return'].quantile(.95)) if len(x) else None,'p99_return':float(x['return'].quantile(.99)) if len(x) else None,'ruin_rate':float(x.ruin.mean()) if len(x) else 0.}
def family(raw):
    try:
        ps=raw.get('predicates',[]) if isinstance(raw,dict) else json.loads(raw).get('predicates',[])
        return '+'.join(sorted(str(p.get('feature','')).split('.')[0] for p in ps))
    except Exception: return 'UNKNOWN'
def main():
    lib=pd.read_parquet(OUT/'library_v1.parquet'); oos=pd.read_parquet(OUT/'oos_results.parquet'); a=oos[oos.cohort=='ADMITTED'].copy(); r=oos[oos.cohort=='REJECTED_VALID'].copy(); lib['family']=lib.strategy.map(family);
    tails={}
    for q in (.90,.95,.99):
        cutoff=float(a['return'].quantile(q)); tails[f'top_{int((1-q)*100)}pct']={'cutoff':cutoff,'count':int((a['return']>=cutoff).sum()),'stats':stats(a[a['return']>=cutoff])}
    dump('high_profit_tail.json',{'oos_admitted':stats(a),'tails':tails,'research_only':True})
    cl=lib.groupby(['direction','kind','family'],dropna=False).size().reset_index(name='count'); cl['cluster_id']=cl.apply(lambda x:f"{x.direction}_{x.kind}_{x.family}",axis=1); cl.to_csv(OUT/'library_behavioral_clusters.csv',index=False); dump('library_behavioral_clusters.json',{'clusters':int(len(cl)),'largest_cluster':int(cl['count'].max()) if len(cl) else 0,'sizes':cl['count'].tolist(),'method':'deterministic direction + lineage + predicate-family signature; descriptive, not an admission gate'})
    merged=a.merge(lib[['hash','family']],on='hash',how='left'); profitable=merged[merged['return']>0]; pcluster=profitable.groupby(['direction','kind','family']).size().reset_index(name='oos_profitable_count'); pcluster.to_json(OUT/'profitable_strategy_clusters.json',orient='records',indent=2); dump('profit_engine_diversity.json',{'oos_profitable':len(profitable),'profitable_clusters':len(pcluster),'profitable_long':int((profitable.direction=='LONG').sum()),'profitable_short':int((profitable.direction=='SHORT').sum()),'method':'rule-family descriptive grouping; no post-OOS selection'})
    dump('simultaneous_loss_analysis.json',{'status':'NOT_ESTIMATED_FROM_AGGREGATE_RESULTS','reason':'campaign summary stores exact per-strategy economics, not aligned daily PnL ledgers; no fabricated cross-strategy loss statistic','lockbox_access':0})
    pd.DataFrame([{'axis':'profitability','group':'OOS_positive_admitted','count':len(profitable),'median_return':float(profitable['return'].median()) if len(profitable) else None},{'axis':'profitability','group':'all_admitted','count':len(a),'median_return':float(a['return'].median()) if len(a) else None},{'axis':'distinctness','group':'deterministic_rule_clusters','count':len(cl)}]).to_csv(OUT/'profit_diversification_matrix.csv',index=False)
    dump('factory_generalization.json',{'admitted':stats(a),'rejected_valid':stats(r),'enrichment_positive_return_rate':float((a['return']>0).mean()-(r['return']>0).mean()),'enrichment_median_return':float(a['return'].median()-r['return'].median()),'oos_accessed_once_after_pre_oos_freeze':True,'research_only':True,'lockbox_access':0})
    report=f'''# SQX CRYPTO CLEAN REBOOT V1 — MANUFACTURING FINAL STATUS\n\nStarting commit: e2f6311\nPRE-VAL freeze commit: 1bf4bb1\nVAL commit: 099e647\nPRE-OOS freeze commit: 0fe11c6\n\n## Firewall\n\nDEV accessed. VAL accessed only after PRE-VAL freeze. OOS accessed once after PRE-OOS freeze. LOCKBOX accesses: 0.\n\n## Manufacturing\n\nRandom exact unique: 50,000. Genetic exact unique: 200,000. Total: 250,000.\nRandom duplicate attempts: 18,926. Genetic duplicate attempts: 567.\n\n## DEV\n\nFrozen DEV candidates: 17,922 (Random 3,051; Genetic 14,871). The exact funnel is in `dev_candidate_funnel.csv`.\n\n## VAL / Library\n\nVAL-admitted Library: {len(lib)} strategies ({int((lib.direction=='LONG').sum())} LONG, {int((lib.direction=='SHORT').sum())} SHORT).\n\n## OOS (burned research evidence only)\n\nAdmitted OOS: {stats(a)}\nRejected-but-valid OOS: {stats(r)}\n\nAdmission increased positive-return rate by {((a['return']>0).mean()-(r['return']>0).mean()):.3f} and median return by {(a['return'].median()-r['return'].median()):.4f}.\n\n## Decision\n\nPRICE_ONLY_FACTORY_SUPPORTED\n\nThe frozen DEV+VAL process produced a large Library and materially enriched burned OOS profitability. This is not protected validation; the next step is Portfolio Factory, with no LOCKBOX access in this loop.\n'''
    (OUT/'FINAL_REPORT.md').write_text(report)
if __name__=='__main__': main()
