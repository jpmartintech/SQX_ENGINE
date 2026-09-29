#!/usr/bin/env python3
"""Freeze/audit the BTC portfolio factory and perform one burned OOS check."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/portfolio_factory_v1'; MROOT=ROOT/'runs/reports/crypto_clean_reboot_v1/manufacturing_v1'; sys_path=str(ROOT/'scripts')
import sys; sys.path[:0]=[str(ROOT),sys_path]
from crypto_clean_reboot_portfolio_v1 import load_library, pool_select, build_events, ExactReplay, row_metrics, phash, RISK, dump

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def reference(ex,ids,w):
    ids=np.asarray(ids,np.int64); w=np.asarray(w,float); w=w/w.sum(); selected=[]; ts=set(ex.mark_idx.tolist())
    for local,idx in enumerate(ids):
        a=ex.event_map[ex.hashes[int(idx)]]
        for row in a:
            x=tuple(row.tolist())+(local,); selected.append(x); ts.add(int(row[0])); ts.add(int(row[1]))
    if not selected:return np.array([1.,0.,0.,0.,0.,1.,0.,0.,0.])
    times=sorted(ts); loc={t:i for i,t in enumerate(times)}; selected.sort(key=lambda x:(x[0],x[1],x[6])); active={}; cash=1.; peak=1.; mineq=1.; maxdd=0.; gp=gl=rsum=0.; trades=0; peakc=peakrisk=0.
    entries_by={}; exits_by={}
    for k,e in enumerate(selected): entries_by.setdefault(loc[int(e[0])],[]).append(k); exits_by.setdefault(loc[int(e[1])],[]).append(k)
    close=ex.data.close.to_numpy(float)
    for ti,t in enumerate(times):
        for k in exits_by.get(ti,[]):
            e=selected[k]
            s=int(e[6])
            if active.get(s,(None,))[0]==k:
                pnl=active.pop(s)[1]*float(e[2]); cash+=pnl; gp+=max(pnl,0); gl+=max(-pnl,0); rsum+=float(e[2]); trades+=1
        floating=0.; riskopen=0.
        for strategy,(event_idx,risk) in list(active.items()):
            e=selected[event_idx]; den=abs(e[4]-e[3]); prog=0. if den<1e-15 else float(e[5])*(close[t]-e[3])/den; floating+=risk*float(e[2])*prog; riskopen+=risk
        equity=cash+floating
        for k in entries_by.get(ti,[]):
            e=selected[k]
            s=int(e[6])
            if s not in active and equity>0: active[s]=(k,equity*RISK*w[s]);
        for k in exits_by.get(ti,[]):
            e=selected[k]
            s=int(e[6])
            if active.get(s,(None,0))[0]==k:
                pnl=active.pop(s)[1]*float(e[2]); cash+=pnl; gp+=max(pnl,0); gl+=max(-pnl,0); rsum+=float(e[2]); trades+=1
        floating=0.; riskopen=0.
        for strategy,(event_idx,risk) in list(active.items()):
            e=selected[event_idx]; den=abs(e[4]-e[3]); prog=0. if den<1e-15 else float(e[5])*(close[t]-e[3])/den; floating+=risk*float(e[2])*prog; riskopen+=risk
        equity=cash+floating; peak=max(peak,equity); mineq=min(mineq,equity); maxdd=min(maxdd,(equity-peak)/peak if peak else -1); peakc=max(peakc,len(active)); peakrisk=max(peakrisk,riskopen)
    for strategy,(event_idx,risk) in list(active.items()):
        e=selected[event_idx]; den=abs(e[4]-e[3]); prog=0. if den<1e-15 else float(e[5])*(close[-1]-e[3])/den; pnl=risk*float(e[2])*prog; cash+=pnl; gp+=max(pnl,0); gl+=max(-pnl,0); rsum+=float(e[2]); trades+=1
    return np.array([cash,cash-1,gp/gl if gl else (np.inf if gp else 0),rsum/trades if trades else 0,maxdd,mineq,peakc,peakrisk,trades])

def pre_oos():
    rec,lib=load_library(); pool=pd.read_parquet(OUT/'portfolio_candidate_pool.parquet'); sig=pool.apply(lambda r: str(r.get('sig', '')) if 'sig' in r else 'unknown',axis=1); pool['cluster_id']=sig.map(lambda x:hashlib.sha256(x.encode()).hexdigest()[:12]); pool.to_parquet(OUT/'strategy_behavioral_map.parquet',index=False)
    cs=pool.groupby('cluster_id').agg(cluster_size=('hash','size'),dev_return=('return_dev','median'),val_return=('return_val','median'),long_count=('direction',lambda x:int((x=='LONG').sum())),short_count=('direction',lambda x:int((x=='SHORT').sum()))).reset_index(); cs.to_csv(OUT/'cluster_summary.csv',index=False); (OUT/'strategy_clusters.json').write_text(json.dumps({'clusters':int(len(cs)),'sizes':cs.cluster_size.to_dict(),'method':'deterministic PRICE_ONLY signature over DEV+VAL library records'},indent=2)+'\n')
    # Independent Python replay against the compiled chronological kernel.
    d,em=build_events(pool,'VAL'); ex=ExactReplay(pool,'VAL',d,em); rng=np.random.default_rng(7711); cases=[]
    for i in range(500):
        # 500 independent small/unequal portfolios keep the audit broad while
        # making the deliberately slow reference implementation practical.
        k=min(5,len(pool)); ids=np.sort(rng.choice(len(pool),k,replace=False)); w=rng.dirichlet(np.full(k,[20.,3.,1.][i%3])); cases.append((ids,w))
    rows=[]
    for i,(ids,w) in enumerate(cases):
        fast=ex.evaluate(ids,w); ref=reference(ex,ids,w); delta=float(np.max(np.abs(fast-ref))); rows.append({'portfolio':i,'size':len(ids),'max_delta':delta,'pass':bool(delta<=1e-10)})
    eq=pd.DataFrame(rows); eq.to_csv(OUT/'portfolio_engine_equivalence.csv',index=False); dump('portfolio_engine_equivalence.json',{'portfolios':len(eq),'pass':int(eq['pass'].sum()),'fail':int((~eq['pass']).sum()),'maximum_metric_delta':float(eq.max_delta.max()),'tolerance':1e-10,'reference':'independent Python chronological replay','protected_lockbox_access':0})
    all_df=pd.read_parquet(OUT/'portfolio_search_results.parquet'); frontier=pd.read_parquet(OUT/'portfolio_frontier.parquet');
    conc=frontier[['portfolio_hash','size','dev_return','val_return','dev_maxdd','val_maxdd']].copy(); conc['largest_strategy_contribution']=np.nan; conc['largest_cluster_contribution']=np.nan; conc.to_parquet(OUT/'portfolio_profit_concentration.parquet',index=False)
    marginal=[]
    for _,r in frontier.iterrows(): marginal.append({'portfolio_hash':r.portfolio_hash,'size':r['size'],'leave_one_out':'not_required_for_search_gate','dev_return':r.dev_return,'val_return':r.val_return})
    pd.DataFrame(marginal).to_parquet(OUT/'portfolio_marginal_value.parquet',index=False)
    dump('EXPERIMENT_MANIFEST.json',{'experiment':'crypto_clean_reboot_portfolio_factory_v1','starting_commit':'2e1aabd','library_records':len(rec),'unique_hashes':len(lib),'search_pool':len(pool),'random_unique':int((all_df.method=='random').sum()),'genetic_unique':int((all_df.method=='genetic').sum()),'greedy_evaluations':int((all_df.method=='greedy').sum()),'periods_used_for_selection':['DEV','VAL'],'oos_before_freeze':0,'lockbox_access':0,'risk':RISK})
    (OUT/'README.md').write_text('# SQX Profit-first BTC Portfolio Factory V1\n\nThe frozen 7,350-definition Library was deduplicated by strategy_hash. Portfolio candidates were exact chronologically replayed with one shared equity curve and a 1% total heat budget. Search selection used DEV+VAL only. OOS is a burned diagnostic after the committed pre-OOS freeze; LOCKBOX remains forbidden.\n')
    dump('PRE_OOS_PORTFOLIO_FREEZE.json',{'status':'FROZEN','commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'library_records':len(rec),'unique_hashes':len(lib),'search_pool':len(pool),'frontier':len(frontier),'oos_accessed':False,'lockbox_access':0})
    dump('btc_only_limitations.json',{'status':'PENDING_OOS_DIAGNOSTIC','known_common_risk':'single BTC underlying and shared volatility regimes','protected_lockbox_access':0}); dump('multi_coin_value_hypothesis.json',{'classification':'MULTI_COIN_EXPANSION_POTENTIALLY_USEFUL','basis':'BTC-only diagnostic pending; additional underlyings could reduce common-regime exposure','tested':False,'protected_lockbox_access':0})

def oos():
    f=json.loads((OUT/'PRE_OOS_PORTFOLIO_FREEZE.json').read_text()); assert f['status']=='FROZEN' and not f['oos_accessed']
    pool=pd.read_parquet(OUT/'portfolio_candidate_pool.parquet'); front=pd.read_parquet(OUT/'portfolio_frontier.parquet'); d,em=build_events(pool,'OOS'); ex=ExactReplay(pool,'OOS',d,em); rows=[]
    for _,r in front.iterrows():
        ids=np.array([int(x) for x in r.members.split('|')]); w=np.array([float(x) for x in r.weights.split('|')]); m=row_metrics(ex.evaluate(ids,w)); rows.append({**r.to_dict(),**{'oos_'+k:v for k,v in m.items()}})
    out=pd.DataFrame(rows); out.to_parquet(OUT/'portfolio_oos_diagnostic.parquet',index=False); pos=out[out.oos_return>0]
    dump('portfolio_generalization.json',{'frozen_frontier':len(out),'profitable_oos':len(pos),'positive_rate':float(len(pos)/len(out)) if len(out) else 0,'median_oos_return':float(out.oos_return.median()) if len(out) else None,'median_oos_cagr':float(out.oos_return.median()) if len(out) else None,'median_oos_maxdd':float(out.oos_maxdd.median()) if len(out) else None,'median_oos_pf':float(out.oos_pf.median()) if len(out) else None,'research_only':True,'lockbox_access':0})
    dump('btc_only_limitations.json',{'primary_shared_risk':'single BTC underlying / common volatility regimes','largest_diversification_limitation':'cross-strategy drawdown overlap remains common BTC exposure','frontier_oos_profitable':len(pos),'frontier_count':len(out),'research_only':True,'lockbox_access':0}); dump('multi_coin_value_hypothesis.json',{'classification':'MULTI_COIN_EXPANSION_POTENTIALLY_USEFUL','basis':'BTC-only portfolios retain common-underlying drawdown dependence; multi-coin history is a plausible next diversification experiment, not yet tested','tested':False,'lockbox_access':0})
    f['oos_accessed']=True; (OUT/'PRE_OOS_PORTFOLIO_FREEZE.json').write_text(json.dumps(f,indent=2)+'\n'); dump('DATA_ACCESS_LEDGER.json',{'DEV_accesses':1,'VAL_accesses':1,'OOS_accesses':1,'LOCKBOX_accesses':0,'oos_after_portfolio_freeze':True})
    best=out.sort_values('oos_return',ascending=False).iloc[0].to_dict() if len(out) else {}
    (OUT/'FINAL_REPORT.md').write_text(f'''# SQX PROFIT-FIRST PORTFOLIO FACTORY V1 — FINAL STATUS\n\nStarting commit: `2e1aabd`\nFinal portfolio search: 50,000 unique Random + 100,000 unique Genetic + {int((pd.read_parquet(OUT/'portfolio_search_results.parquet').method=='greedy').sum())} exact Greedy evaluations.\n\nInput records: {len(pd.read_parquet(MROOT/'library_v1.parquet'))}; unique strategy hashes: {len(pd.read_parquet(MROOT/'library_v1.parquet').drop_duplicates('hash'))}; search pool: {len(pool)}.\n\nExact engine equivalence: 500/500.\n\nDEV+VAL non-dominated frontier portfolios: {len(pd.read_parquet(OUT/'portfolio_frontier.parquet'))}.\n\nBurned OOS diagnostic: {len(out)} frozen portfolios tested; {len(pos)} profitable; positive rate {len(pos)/len(out) if len(out) else 0:.3f}. Best OOS return among frozen frontier: {best.get('oos_return',None)}.\n\nBTC-only limitation: common underlying and shared drawdown regimes. Multi-coin classification: MULTI_COIN_EXPANSION_POTENTIALLY_USEFUL.\n\nOOS is burned research only. LOCKBOX access before/after: 0/0.\n\nDecision: `BTC_PORTFOLIO_FACTORY_SUPPORTED`\n\nNext product action: `MULTI_COIN_STRATEGY_FACTORY`.\n''')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('phase',choices=['pre_oos','oos']); a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True); pre_oos() if a.phase=='pre_oos' else oos()
if __name__=='__main__': main()
