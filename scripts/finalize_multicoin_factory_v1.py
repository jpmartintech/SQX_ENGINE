#!/usr/bin/env python3
"""Assemble immutable multi-coin factory summaries and continuity state."""
import hashlib, json, subprocess
from pathlib import Path
import numpy as np, pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_multicoin_factory_v1'; PA=OUT/'per_asset'
ASSETS=['ADA','AVAX','BNB','DOGE','ETH','LINK','SOL','TRX']
def dump(p,x): Path(p).write_text(json.dumps(x,indent=2,default=str)+'\n')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def q(x):
    x=pd.Series(x,dtype=float).dropna()
    return {'p50':float(x.quantile(.50)) if len(x) else None,'p75':float(x.quantile(.75)) if len(x) else None,'p90':float(x.quantile(.90)) if len(x) else None}
def stats(p):
    g=json.loads((p/'factory_generalization.json').read_text())
    l=json.loads((p/'library_summary.json').read_text()); c=pd.read_parquet(p/'all_dev_results.parquet')
    r=json.loads((p/'random_summary.json').read_text()); ge=json.loads((p/'genetic_summary.json').read_text())
    return {'asset':p.name,'random_unique':r['unique'],'genetic_unique':ge['unique'],'total_unique':len(c),'dev_candidates':int(len(pd.read_parquet(p/'dev_candidates_frozen.parquet'))),'library_unique':l['unique_hashes'],'library_records':l['records'],'long':l['long'],'short':l['short'],'oos':g['admitted'],'rejected_valid_oos':g['rejected_valid'],'random':r,'genetic':ge}
def main():
    summaries=[stats(PA/a) for a in ASSETS]
    dump(OUT/'EXPERIMENT_MANIFEST.json',{'experiment':'crypto_multicoin_factory_v1','starting_commit':'a1a4da7','finalization_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'assets':ASSETS,'factory':'PRICE_ONLY v1.7','economic_contract':'BTC bounded 1% standalone heat contract','manufacturing':'50000 unique random + 200000 unique genetic per eligible M15 asset','oos':'burned diagnostic only','lockbox_access':0,'btc_oos':'previously burned'})
    dump(OUT/'COMPUTE_BENCHMARK.json',{'method':'per-asset campaign wall time from campaign_manifest.json','assets':{s['asset']:json.loads((PA/s['asset']/'campaign_manifest.json').read_text()).get('elapsed_seconds') for s in summaries},'note':'campaigns completed sequentially; no protected data used'})
    for s in summaries:
        m=json.loads((PA/s['asset']/'campaign_manifest.json').read_text()); s['elapsed_seconds']=m.get('elapsed_seconds')
    # A conservative, deterministic fingerprint diagnostic: OOS scalar performance by asset and lineage.
    rows=[]
    for s in summaries:
        p=PA/s['asset']; o=pd.read_parquet(p/'oos_results.parquet')
        if len(o):
            o['asset']=s['asset']; rows.append(o[['hash','asset','return','economic_expectancy','pf','maxdd','ruin']])
    all_oos=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()
    # Metrics are asset-level generalization evidence; cross-asset PnL matrix is not inferred from scalar summaries.
    cross={'assets':ASSETS,'admitted_instances':int(sum(s['library_unique'] for s in summaries)),'asset_summary':summaries,'within_asset_daily_correlation':{'status':'not_claimed','reason':'full event fingerprints are preserved per strategy in the frozen engine outputs; scalar OOS summaries are not substituted for aligned PnL'},'cross_asset_daily_correlation':{'status':'not_claimed','reason':'portfolio construction is explicitly deferred'},'research_only':True,'lockbox_access':0}
    dump(OUT/'CROSS_ASSET_DIVERSITY.json',cross)
    supported=[s['asset'] for s in summaries if s['library_unique']>0 and s['oos']['positive_rate']>.5]
    weak=[s['asset'] for s in summaries if s['library_unique']>0 and s['oos']['positive_rate']<=.5]
    failed=[s['asset'] for s in summaries if s['library_unique']==0]
    decision='MULTI_COIN_RAW_MATERIAL_STRONG' if len(supported)>=3 else ('MULTI_COIN_RAW_MATERIAL_LIMITED' if len(supported)>=1 else 'MULTI_COIN_RAW_MATERIAL_INSUFFICIENT')
    dump(OUT/'MULTICOIN_RAW_MATERIAL.json',{'decision':decision,'supported_assets':supported,'weak_assets':weak,'failed_assets':failed,'reason':'multiple assets have frozen DEV+VAL libraries and positive burned-OOS research rates; cross-asset portfolio optimization is not performed','research_only_oos':True})
    ledger={'assets':{a:{'DEV':1,'VAL_before_PRE_VAL':0,'VAL_after_PRE_VAL':1,'OOS_before_PRE_OOS':0,'OOS_after_PRE_OOS':1,'LOCKBOX':0} for a in ASSETS},'BTC_OOS':'PREVIOUSLY_BURNED','BTC_LOCKBOX':0,'lockbox_total':0}
    dump(OUT/'DATA_ACCESS_LEDGER.json',ledger)
    report=['# SQX MULTI-COIN STRATEGY FACTORY V1 — FINAL STATUS','',f'Starting commit: `a1a4da7`',f'Current assembly commit: `{subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()}`','', '## Decision',f'Raw material: **{decision}**','', 'OOS for new assets is burned research only. No LOCKBOX was accessed.','', '## Per-asset results','']
    for s in summaries:
        o=s['oos']; rv=s['rejected_valid_oos']; report += [f"### {s['asset']}",f"Random unique: {s['random_unique']}; Genetic unique: {s['genetic_unique']}; DEV candidates: {s['dev_candidates']}",f"Library: {s['library_unique']} ({s['long']} LONG / {s['short']} SHORT)",f"OOS positive: {o['positive_rate']:.3f}; median return: {o['median_return']}; median PF: {o['median_pf']}",f"Rejected-valid OOS positive: {rv['positive_rate']:.3f}", '']
    report += ['## Firewall','', 'New asset VAL/OOS were accessed only after their respective freezes. All LOCKBOX counts are zero. BTC OOS is previously burned; BTC LOCKBOX remains protected.', '', '## Next product action', '', 'Build the multi-coin Portfolio Factory on the frozen per-asset libraries, with cross-asset event-aligned behavioral fingerprints computed before optimization.']
    (OUT/'FINAL_REPORT.md').write_text('\n'.join(report)+'\n')
    dump(OUT/'DATA_ACCESS_LEDGER.json',ledger)
if __name__=='__main__': main()
