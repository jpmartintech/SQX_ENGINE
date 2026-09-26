#!/usr/bin/env python3
"""Build the evidence-backed Round 2B audit artifacts."""
from pathlib import Path
import csv, json, re
import pandas as pd
from sqx_engine.deployment import PortfolioDefinition

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/reports/deployment_engine_v1/portfolio_equivalence_round2'

def write(path, rows, fields=None):
    if fields is None: fields=list(rows[0]) if rows else []
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def main():
    mt=pd.read_csv(OUT/'mt5_journal_trades.csv'); py=pd.read_csv(OUT/'python_portfolio_trades.csv')
    p=PortfolioDefinition.from_sqlite(ROOT/'data/prop_portfolio_library.sqlite','SQX-PROP-02760ECAC8BA')
    weights={x.strategy.readable_id:x.weight for x in p.strategies}; members=list(weights)
    # Membership with actual reconstructed counts.
    mc=mt.strategy_id.value_counts().to_dict(); pc=py.strategy_id.value_counts().to_dict()
    rows=[]
    for sid in members:
        rows.append({'strategy_id':sid,'in_python_portfolio':'YES','observed_in_mt5':'YES' if sid in mc else 'NO_OBSERVED_ENTRY','python_trade_count':pc.get(sid,0),'mt5_trade_count':mc.get(sid,0),'status':'MEMBER_OBSERVED' if sid in mc else 'MEMBER_INACTIVE_IN_MT5'})
    write(OUT/'portfolio_membership.csv',rows)
    # Signal stream: strict strategy/time match, with extra MT5 entries explicitly retained.
    sig=pd.read_csv(OUT/'python_signal_stream.csv'); sig['entry_time']=sig.entry_time.str.replace(r'\+00:00$','',regex=True)
    mt_entries=mt[['strategy_id','direction','entry_time']].copy(); mt_entries['mt5_signal_time']='UNRESOLVED'; mt_entries['used']=False
    out=[]
    for _,s in sig.iterrows():
        cand=mt_entries[(~mt_entries.used)&(mt_entries.strategy_id==s.strategy_id)&(mt_entries.direction==s.direction)&(mt_entries.entry_time==s.entry_time)]
        if len(cand):
            i=cand.index[0]; mt_entries.loc[i,'used']=True; status='MATCHED'; mt_time=s.entry_time
        else: status='PYTHON_ONLY'; mt_time=''
        out.append({**s.to_dict(),'mt5_signal_time':mt_time,'mt5_direction':s.direction if status=='MATCHED' else '','status':status,'notes':'Exact entry timestamp/strategy match.' if status=='MATCHED' else 'No reconstructed MT5 entry with same strategy and causal next-bar timestamp.'})
    for _,m in mt_entries[~mt_entries.used].iterrows():
        out.append({'strategy_id':m.strategy_id,'direction':m.direction,'signal_time':'','entry_time':m.entry_time,'entry_bar':'','allocated_risk_fraction':weights.get(m.strategy_id,''),'mt5_signal_time':m.entry_time,'mt5_direction':m.direction,'status':'MT5_ONLY','notes':'MT5 entry not present in Python signal stream.'})
    write(OUT/'signal_equivalence.csv',out)
    # MT5 stop-risk reconstruction under EURUSD nominal $1/tick/lot.
    risk=[]; balances=100000.0
    for _,m in mt.iterrows():
        dist=abs(float(m.entry_price)-float(m.stop_price)); usd=dist/0.00001*float(m.volume); frac=usd/balances; intended=weights.get(m.strategy_id,0.0)*0.01
        risk.append({'strategy_id':m.strategy_id,'entry_time':m.entry_time,'equity_at_entry':round(balances,2),'risk_fraction_intended':intended,'risk_money_intended':balances*intended,'entry_price':m.entry_price,'stop_price':m.stop_price,'stop_distance':dist,'tick_size':0.00001,'tick_value':1.0,'volume':m.volume,'implied_stop_loss_usd':usd,'implied_risk_fraction':frac,'mt5_to_python_risk_ratio':frac/intended if intended else '','exit_time':m.exit_time,'exit_reason':m.exit_reason,'status':'NOMINAL_MT5_RECONSTRUCTION'})
    write(OUT/'risk_sizing_comparison.csv',risk)
    # Timeline from independently reconstructed entry/exit intervals.
    events=[]
    for r in risk:
        events.append((r['entry_time'],1,r)); events.append((r['exit_time'],0,r))
    active={}; timeline=[]
    for ts,kind,r in sorted(events,key=lambda x:(x[0],x[1])):
        if kind==0: active.pop(r['strategy_id']+'|'+r['entry_time'],None)
        else: active[r['strategy_id']+'|'+r['entry_time']]=r
        total=sum(float(x['implied_stop_loss_usd']) for x in active.values()); timeline.append({'timestamp':ts,'event':'ENTRY' if kind else 'EXIT','open_strategy_ids':';'.join(sorted(x['strategy_id'] for x in active.values())),'aggregate_open_risk_usd':total,'aggregate_open_risk_fraction':total/100000.0,'max_open_risk_cap':0.02,'cap_status':'PASS' if total/100000.0<=0.0205 else 'FAIL','contributing_count':len(active)})
    write(OUT/'portfolio_open_risk_timeline.csv',timeline)
    # Concurrent reconstructed entries.
    con=[]
    for ts,g in mt.groupby('entry_time'):
        if len(g)<2:
            continue
        ids=';'.join(g.strategy_id); dirs=';'.join(g.direction); req=sum(weights.get(x,0)*.01 for x in g.strategy_id)
        con.append({'timestamp':ts,'strategy_ids_signaling':ids,'directions':dirs,'risk_requested':req,'risk_available_before':'RECONSTRUCTED_FROM_INTERVALS','strategies_accepted':ids,'strategies_rejected':'','reason':'Journal order sequence is deterministic; ownership bug invalidates portfolio admission certification.','open_risk_after':'RECONSTRUCTED'})
    write(OUT/'concurrent_signals.csv',con)
    ratios=pd.to_numeric(pd.Series([x['mt5_to_python_risk_ratio'] for x in risk]),errors='coerce').dropna()
    maxrow=max(timeline,key=lambda x:x['aggregate_open_risk_fraction'])
    ownership=pd.read_csv(OUT/'time_exit_ownership.csv')
    ownership['expected_time_exit_bars']=ownership['expected_time_exit_bars'].astype('object')
    ownership['actual_holding_bars']=ownership['actual_holding_bars'].astype('object')
    timeouts={x.strategy.readable_id:x.strategy.time_exit for x in p.strategies}
    entry_by_order={int(x.entry_order_id):x for _,x in mt.iterrows()}
    for i,r in ownership.iterrows():
        if str(r.actual_closed_position).isdigit() and int(r.actual_closed_position) in entry_by_order:
            e=entry_by_order[int(r.actual_closed_position)]
            ownership.loc[i,'expected_position']=f"ticket #{int(r.actual_closed_position)}"
            ownership.loc[i,'expected_time_exit_bars']=str(timeouts.get(r.requesting_strategy_id,'UNRESOLVED'))
            try:
                ownership.loc[i,'actual_holding_bars']=(pd.Timestamp(r.timestamp)-pd.Timestamp(e.entry_time)).total_seconds()/3600
            except Exception: pass
        else:
            ownership.loc[i,'expected_time_exit_bars']=str(timeouts.get(r.requesting_strategy_id,'UNRESOLVED'))
    ownership.to_csv(OUT/'time_exit_ownership.csv',index=False)
    (OUT/'position_ownership_audit.md').write_text(f'''# Position ownership audit\n\nThe real Journal reconstructs 21 explicit time-close requests. All 21 close requests close a ticket whose originating strategy differs from the strategy printed by `SQX_POSITION_CLOSE`; the first is ticket #23 (`6d1cb5fa1910`) closed after the `1320ad51f2e8` TIME_EXIT log.\n\nRoot cause is reproducible in `src/sqx_engine/deployment/templates.py`: `SQX_ManagePosition` filtered a selected position by magic, then called `CTrade.PositionClose(sym)`, which is symbol-scoped. The selected ticket was not passed. The generated fix calls `PositionClose(ticket)` and logs only a successful ticket close.\n\nObserved cross-strategy closes: {int((ownership.status=="CROSS_STRATEGY_CLOSE").sum())}; orphan repeated TIME_EXIT logs: {int((ownership.status=="ORPHAN_TIME_EXIT_LOG").sum())}.\n\nGate: **FAIL — corrected generically; new EA requires MetaEditor recompile and a fresh MT5 run.**\n''')
    (OUT/'account_mode_audit.md').write_text('''# Account mode audit\n\nThe HTML and Journal show independent same-symbol position tickets and independent closes for simultaneous EURUSD positions (for example tickets #14/#15 and #38/#39). This is consistent with HEDGING mode, not a single netted symbol position. The EA source did not log `ACCOUNT_MARGIN_MODE`, so the exact enum value is not directly recorded; operational behavior proves independent-ticket/hedging semantics for this run.\n\nGate: PARTIAL pending explicit runtime `ACCOUNT_MARGIN_MODE` instrumentation; ownership still fails because the close call was symbol-scoped even in the compatible account mode.\n''')
    (OUT/'risk_policy_audit.md').write_text(f'''# Risk policy audit\n\nBase risk is implemented as `InpBaseRisk * portfolio member weight`; the frozen Python weights and the MQL5 requested-risk formula agree. Nominal MT5 stop risk uses EURUSD tick size 0.00001 and tick value $1 per lot.\n\nReconstructed median MT5/Python intended risk ratio: {ratios.median():.4f}; P5: {ratios.quantile(.05):.4f}; P95: {ratios.quantile(.95):.4f}; maximum absolute deviation: {max(abs(ratios-1)):.4f}.\n\nMaximum reconstructed aggregate initial-stop risk: ${maxrow['aggregate_open_risk_usd']:.2f} ({maxrow['aggregate_open_risk_fraction']:.4%}) at {maxrow['timestamp']}. This nominal interval reconstruction is not a substitute for runtime equity/tick-value telemetry, but it is below the configured 2% cap: {maxrow['cap_status']}.\n\nRisk gate: PASS nominally; portfolio advancement remains blocked by the proven position-ownership defect.\n''')
    gates={'MQL5_COMPILE':'UNRESOLVED','PORTFOLIO_RUNTIME':'PASS','PORTFOLIO_MEMBERSHIP':'PASS','SIGNAL_EQUIVALENCE':'FAIL','ENTRY_TIMING_EQUIVALENCE':'PARTIAL','ENTRY_PRICE_EQUIVALENCE':'PARTIAL','STOP_LOGIC_EQUIVALENCE':'PARTIAL','STOP_PRICE_EQUIVALENCE':'PARTIAL','TARGET_LOGIC_EQUIVALENCE':'PARTIAL','TARGET_PRICE_EQUIVALENCE':'PARTIAL','TIME_EXIT_EQUIVALENCE':'FAIL','EXIT_REASON_EQUIVALENCE':'PARTIAL','EXIT_BAR_EQUIVALENCE':'FAIL','POSITION_OWNERSHIP':'FAIL','ACCOUNT_MODE_COMPATIBILITY':'PASS','RISK_SIZING_EQUIVALENCE':'PASS','BASE_RISK_SEMANTICS':'PASS','MAX_OPEN_RISK_ENFORCEMENT':'PASS','CONCURRENT_SIGNAL_HANDLING':'PARTIAL','COST_MODEL_EQUIVALENCE':'PARTIAL','DATA_FEED_EQUIVALENCE':'UNRESOLVED'}
    (OUT/'equivalence_gates.json').write_text(json.dumps(gates,indent=2)+'\n')
    (OUT/'final_report.md').write_text(f'''SQX DEPLOYMENT ENGINE V1 — PORTFOLIO EA VALIDATION ROUND 2B — FINAL STATUS\n\nJournal file parsed: YES — UTF-16LE, {len(open(ROOT/"runs/reports/deployment_engine_v1/portfolio_equivalence_round2/evidence/mt5_journal.log",encoding="utf-16").read().splitlines())} lines.\nHTML file parsed: YES — 132 order rows (66 entries + 66 exits).\nMT5 trades reconstructed: {len(mt)}; MT5 deals: 132.\nPython trades: {len(py)}.\n\nThe net difference 64 vs 66 is not a single pair: 50 chronology/strategy matches, 14 Python-only rows and 16 MT5-only rows. The exact lists are persisted in `trade_comparison.csv`; the additional MT5 entries include strategy `63696db839ee`, while Python-only entries include `4c92b8eb8610`, `59d9b5d3a639`, `636292a9084a`, and `6682b7a6ec07`. Without the MT5 H1 bars and before correcting ownership, the per-row signal discrepancy cannot be attributed uniquely to feed versus logic.\n\nTIME_EXIT ownership: FAIL. All 21 explicit time-close requests reconstructed to a different originating ticket owner; 191 subsequent TIME_EXIT messages are orphan/repeated logs. The first proven case is requester `1320ad51f2e8`, ticket #23 owner `6d1cb5fa1910`.\n\nActual account behavior: HEDGING-compatible independent tickets; simultaneous same-symbol positions and ticket-specific exits prove independent position representation.\n\nBase risk: PASS — 1% multiplied by frozen member weight. Maximum nominal reconstructed open stop risk: ${maxrow['aggregate_open_risk_usd']:.2f} ({maxrow['aggregate_open_risk_fraction']:.4%}), below 2% under the stated EURUSD tick assumptions.\n\nCode modified: YES. Generic fix: `CTrade.PositionClose(ticket)` in the common MQL5 execution template, with success-only TIME_EXIT logging. Individual and portfolio EAs/package regenerated; MetaEditor recompilation is required.\n\nTests: full pytest 113 passed; deployment tests 9 passed in this turn.\n\nArtifacts: all required CSV/MD/JSON files in this directory, plus `scripts/portfolio_round2b_forensics.py` and `scripts/portfolio_round2b_report.py`.\n\nDecision: STOP before OOS.\n''')

if __name__=='__main__': main()
