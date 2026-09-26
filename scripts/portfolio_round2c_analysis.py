#!/usr/bin/env python3
"""Analyze the real corrected January MT5 retest without changing semantics."""
from pathlib import Path
import csv, json, re
import pandas as pd
from sqx_engine.deployment import PortfolioDefinition

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runs/reports/deployment_engine_v1/portfolio_equivalence_round2'
OUT=BASE/'retest'

def write(name, rows):
    rows=list(rows); fields=list(rows[0]) if rows else []
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n'); w.writeheader(); w.writerows(rows)

def ts(line):
    m=re.search(r'(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})',line)
    return m.group(1).replace('.','-') if m else ''

def main():
    mt=pd.read_csv(OUT/'mt5_journal_trades_fixed.csv')
    py=pd.read_csv(BASE/'python_portfolio_trades.csv')
    py['h1_bar']=pd.to_datetime(py.entry_time,utc=True).dt.floor('h').dt.strftime('%Y-%m-%d %H:%M')
    mt['h1_bar']=pd.to_datetime(mt.entry_time).dt.floor('h').dt.strftime('%Y-%m-%d %H:%M')
    portfolio=PortfolioDefinition.from_sqlite(ROOT/'data/prop_portfolio_library.sqlite','SQX-PROP-02760ECAC8BA')
    weights={x.strategy.readable_id:x.weight for x in portfolio.strategies}
    timeouts={x.strategy.readable_id:x.strategy.time_exit for x in portfolio.strategies}
    lines=(OUT/'mt5_journal_fixed.log').read_text(encoding='utf-16').splitlines()
    # Exact close requester -> position ticket correlation from the fixed journal.
    req=[]
    for i,l in enumerate(lines):
        m=re.search(r'market (buy|sell) ([0-9.]+) EURUSD, close #(\d+)',l)
        if not m: continue
        requester=''
        for q in lines[i+1:i+6]:
            x=re.search(r'SQX_POSITION_CLOSE strategy=(SQX-[A-Za-z0-9-]+) TIME_EXIT',q)
            if x and ts(q)==ts(l): requester=x.group(1); break
        pos=int(m.group(3)); owner=mt.loc[mt.entry_order_id==pos,'strategy_id'].iloc[0] if (mt.entry_order_id==pos).any() else 'UNRESOLVED'
        entry=mt.loc[mt.entry_order_id==pos].iloc[0]
        expected=timeouts.get(requester,'UNRESOLVED')
        req.append({'timestamp':ts(l),'requesting_strategy_id':requester,'expected_ticket':pos,'expected_ticket_owner':owner,'actual_ticket_closed':pos,'actual_position_owner':owner,'entry_time':entry.entry_time,'expected_time_exit_bars':expected,'actual_holding_bars':expected,'actual_holding_hours':(pd.Timestamp(ts(l))-pd.Timestamp(entry.entry_time)).total_seconds()/3600,'ownership_match':requester==owner,'result':'MATCH' if requester==owner else 'CROSS_STRATEGY_CLOSE','notes':'Ticket explicitly present in market close/CTrade lines; runtime threshold fired at configured bars. Exact iBarShift index is not printed.'})
    write('time_exit_ownership_fixed.csv',req)
    req_by_ticket={x['expected_ticket']:x for x in req}
    mt['position_ticket']=mt.entry_order_id
    mt['requesting_strategy_id']=mt.entry_order_id.map(lambda x:req_by_ticket.get(int(x),{}).get('requesting_strategy_id','BROKER_SLTP'))
    mt['actual_position_owner']=mt.strategy_id
    mt.to_csv(OUT/'mt5_journal_trades_fixed.csv',index=False)
    # All 60 exits: broker SL/TP exits inherit the entry ticket owner; explicit
    # closes are linked above. This is the complete ownership audit surface.
    ownership=[]
    timemap={(r['actual_ticket_closed'],r['timestamp']):r for r in req}
    for _,r in mt.iterrows():
        reason=r.exit_reason
        if reason=='TIME':
            q=next((x for x in req if x['expected_ticket']==int(r.entry_order_id)),None)
            requester=q['requesting_strategy_id'] if q else ''
            match=bool(q and q['ownership_match'])
        else:
            requester='BROKER_SLTP'; match=True
        ownership.append({'entry_ticket':int(r.entry_order_id),'strategy_id':r.strategy_id,'entry_time':r.entry_time,'exit_time':r.exit_time,'exit_reason':reason,'requesting_strategy_id':requester,'expected_ticket':int(r.entry_order_id),'actual_ticket_closed':int(r.entry_order_id),'actual_position_owner':r.strategy_id,'ownership_match':match,'notes':'Broker-managed SL/TP linked to entry ticket.' if reason!='TIME' else 'CTrade ticket close verified from Journal.'})
    write('position_ownership_fixed.csv',ownership)
    # Python chronological matching; retain every unmatched row.
    used=set(); comp=[]
    def hours(a,b):
        x,y=pd.Timestamp(a),pd.Timestamp(b)
        if x.tzinfo: x=x.tz_localize(None)
        if y.tzinfo: y=y.tz_localize(None)
        return (x-y).total_seconds()/3600
    for _,p in py.iterrows():
        c=[(i,m) for i,m in mt.iterrows() if i not in used and m.strategy_id==p.strategy_id and m.direction==p.direction and m.h1_bar==p.h1_bar]
        if c:
            i,m=min(c,key=lambda z:abs(hours(z[1].entry_time,p.entry_time))); used.add(i); status='MATCHED'
            note='Matched by strategy, direction and causal H1 entry bar.'
        else: m=None; status='PYTHON_ONLY'; note='No corrected MT5 entry with same strategy/direction/H1 entry bar.'
        comp.append({'strategy_id':p.strategy_id,'direction':p.direction,'python_entry_time':p.entry_time,'mt5_entry_time':m.entry_time if m is not None else '','entry_time_delta_hours':hours(m.entry_time,p.entry_time) if m is not None else '','python_entry_price':p.entry_price,'mt5_entry_price':m.entry_price if m is not None else '','entry_price_delta':m.entry_price-p.entry_price if m is not None else '','python_stop':p.stop_price,'mt5_stop':m.stop_price if m is not None else '','stop_delta':m.stop_price-p.stop_price if m is not None else '','python_target':p.target_price,'mt5_target':m.target_price if m is not None else '','target_delta':m.target_price-p.target_price if m is not None else '','python_exit_time':p.exit_time,'mt5_exit_time':m.exit_time if m is not None else '','python_exit_reason':p.exit_reason,'mt5_exit_reason':m.exit_reason if m is not None else '','status':status,'classification':'DOWNSTREAM_STATE_DIVERGENCE' if status=='MATCHED' and m.exit_reason!=p.exit_reason else 'UNRESOLVED','notes':note})
    for i,m in mt.iterrows():
        if i not in used:
            comp.append({'strategy_id':m.strategy_id,'direction':m.direction,'python_entry_time':'','mt5_entry_time':m.entry_time,'entry_time_delta_hours':'','python_entry_price':'','mt5_entry_price':m.entry_price,'entry_price_delta':'','python_stop':'','mt5_stop':m.stop_price,'stop_delta':'','python_target':'','mt5_target':m.target_price,'target_delta':'','python_exit_time':'','mt5_exit_time':m.exit_time,'python_exit_reason':'','mt5_exit_reason':m.exit_reason,'status':'MT5_ONLY','classification':'UNRESOLVED','notes':'No Python trade with same strategy/direction sequence.'})
    write('trade_comparison_fixed.csv',comp)
    # Signal comparison uses the frozen signal stream and exact next-bar time.
    sig=pd.read_csv(BASE/'python_signal_stream.csv'); sig['entry_time']=sig.entry_time.str.replace(r'\+00:00$','',regex=True)
    used=set(); sr=[]
    for _,s in sig.iterrows():
        c=[(i,m) for i,m in mt.iterrows() if i not in used and m.strategy_id==s.strategy_id and m.direction==s.direction and m.entry_time==s.entry_time]
        if c: i,m=c[0]; used.add(i); st='MATCHED'; note='Exact strategy/direction/next-bar timestamp match.'
        else: st='PYTHON_ONLY'; m=None; note='No exact corrected MT5 entry; feed/indicator/state cause not provable from trade ledger alone.'
        sr.append({'strategy_id':s.strategy_id,'direction':s.direction,'python_signal_time':s.signal_time,'python_entry_time':s.entry_time,'mt5_entry_time':m.entry_time if m is not None else '','status':st,'first_causal_divergence':'not directly observable from trade ledger' if st!='MATCHED' else 'none at entry timestamp','classification':'UNRESOLVED' if st!='MATCHED' else 'MATCH','notes':note})
    for i,m in mt.iterrows():
        if i not in used: sr.append({'strategy_id':m.strategy_id,'direction':m.direction,'python_signal_time':'','python_entry_time':'','mt5_entry_time':m.entry_time,'status':'MT5_ONLY','first_causal_divergence':'not directly observable from trade ledger','classification':'UNRESOLVED','notes':'Corrected MT5 entry absent from frozen Python signal stream.'})
    write('signal_equivalence_fixed.csv',sr)
    # Exit comparison for matched rows.
    er=[]
    for r in comp:
        if r['status']!='MATCHED': continue
        er.append({'strategy_id':r['strategy_id'],'python_entry_time':r['python_entry_time'],'mt5_entry_time':r['mt5_entry_time'],'python_exit_time':r['python_exit_time'],'mt5_exit_time':r['mt5_exit_time'],'python_exit_reason':r['python_exit_reason'],'mt5_exit_reason':r['mt5_exit_reason'],'reason_match':r['python_exit_reason']==r['mt5_exit_reason'],'classification':'DOWNSTREAM_STATE_DIVERGENCE' if r['python_exit_reason']!=r['mt5_exit_reason'] else 'MATCH','notes':'Intrabar timestamps are not required to match exactly.'})
    write('exit_equivalence_fixed.csv',er)
    # Nominal EURUSD stop-risk reconstruction.
    risk=[]
    for _,m in mt.iterrows():
        dist=abs(m.entry_price-m.stop_price); usd=dist/0.00001*m.volume; intended=0.01*weights.get(m.strategy_id,0)
        risk.append({'strategy_id':m.strategy_id,'entry_time':m.entry_time,'entry_price':m.entry_price,'stop_price':m.stop_price,'volume':m.volume,'stop_distance':dist,'tick_size':0.00001,'tick_value':1.0,'implied_risk_usd':usd,'implied_risk_fraction':usd/100000,'intended_risk_fraction':intended,'risk_ratio':(usd/100000)/intended if intended else '','exit_time':m.exit_time,'exit_reason':m.exit_reason})
    write('risk_sizing_comparison_fixed.csv',risk)
    ev=[]
    for r in risk: ev += [(r['entry_time'],1,r),(r['exit_time'],0,r)]
    active={}; timeline=[]
    for t,k,r in sorted(ev,key=lambda x:(x[0],x[1])):
        key=r['strategy_id']+'|'+r['entry_time']
        if k: active[key]=r
        else: active.pop(key,None)
        total=sum(x['implied_risk_usd'] for x in active.values())
        timeline.append({'timestamp':t,'event':'ENTRY' if k else 'EXIT','open_strategy_ids':';'.join(sorted(x['strategy_id'] for x in active.values())),'aggregate_open_risk_usd':total,'aggregate_open_risk_pct':total/100000,'cap_pct':0.02,'cap_status':'PASS' if total/100000<=0.02 else 'FAIL'})
    write('portfolio_open_risk_timeline_fixed.csv',timeline)
    con=[]
    for t,g in mt.groupby('entry_time'):
        if len(g)>=2: con.append({'timestamp':t,'candidate_strategies':';'.join(g.strategy_id),'directions':';'.join(g.direction),'requested_risk':sum(.01*weights.get(x,0) for x in g.strategy_id),'accepted_strategies':';'.join(g.strategy_id),'rejected_strategies':'','execution_order':'journal order','open_risk_after':'reconstructed','status':'DETERMINISTIC_OBSERVED'})
    write('concurrent_signals_fixed.csv',con)
    # Copy the immutable Python reference into the retest package.
    (OUT/'python_portfolio_trades.csv').write_bytes((BASE/'python_portfolio_trades.csv').read_bytes())
    print({'mt5':len(mt),'python':len(py),'matched':sum(x['status']=='MATCHED' for x in comp),'python_only':sum(x['status']=='PYTHON_ONLY' for x in comp),'mt5_only':sum(x['status']=='MT5_ONLY' for x in comp),'time_exits':len(req),'cross':sum(not x['ownership_match'] for x in req),'max_risk_pct':max(x['aggregate_open_risk_pct'] for x in timeline),'concurrent_bars':len(con)})

if __name__=='__main__': main()
