"""Forensic replay/comparison for the operator-provided MT5 run."""
from __future__ import annotations
import csv, json, sqlite3
from dataclasses import replace
from datetime import timezone
from pathlib import Path
import pandas as pd
from sqx_engine.strategy import StrategyDefinition
from sqx_engine.features import prepare_features
from sqx_engine.backtest.fast import FastEvaluator

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/reports/deployment_engine_v1/mt5_equivalence_round1'; OUT.mkdir(parents=True,exist_ok=True)
SID='SQX-EURUSD-H1-1320ad51f2e8'; DATA=ROOT/'data/derived/EURUSD_H1_11d571e8bb3d_143197.csv'
with sqlite3.connect(ROOT/'library/strategies.sqlite') as db:
    raw=db.execute('select * from strategies where strategy_id=?',(SID,)).fetchone()
    cols=[x[1] for x in db.execute('pragma table_info(strategies)')]
row=dict(zip(cols,raw)); strategy=replace(StrategyDefinition.from_json(row['strategy_json']),strategy_id=SID)
definition={k:getattr(strategy,k) for k in ('market','timeframe','direction','logic','atr_period','stop_atr','target_atr','time_exit','strategy_id','grammar_version')}
definition['canonical_hash']=strategy.canonical_hash; definition['predicate_count']=len(strategy.predicates); definition['predicates']=[p.to_dict() for p in strategy.predicates]
definition['exit_semantics']={'take_profit_defined':True,'take_profit_distance':'ATR(signal_bar) * target_atr','time_exit_bars':strategy.time_exit,'python_priority':'STOP, TARGET, TIME'}
(OUT/'strategy_definition.json').write_text(json.dumps(definition,indent=2,default=str)+'\n')

df=pd.read_csv(DATA,parse_dates=['timestamp']); features=prepare_features(df,grammar_version=strategy.grammar_version)
start=int(df.index[df.timestamp>=pd.Timestamp('2024-01-01',tz='UTC')][0]); end=int(df.index[df.timestamp>=pd.Timestamp('2024-02-01',tz='UTC')][0])
ev=FastEvaluator(df,features,initial_capital=100000,spread=0,slippage=0,engine='python'); result=ev.evaluate(strategy,start=start,end=end,rich=True); atr=features['atr_14'];
def iso(x): return pd.Timestamp(x).isoformat()
py=[]
for t in result.trades:
    ei=int(df.index[df.timestamp==t['entry_time']][0]); si=ei-1; xi=int(df.index[df.timestamp==t['exit_time']][0]); risk=float(atr[si]*strategy.stop_atr); ep=float(df.open[ei]); sl=ep-risk; tp=ep+float(atr[si]*strategy.target_atr)
    xp={'STOP':sl,'TARGET':tp,'TIME':float(df.close[xi]),'END':float(df.close[xi])}[t['reason']]
    py.append({'signal_bar_time':iso(df.timestamp[si]),'entry_time':iso(t['entry_time']),'direction':t['direction'],'entry_price':ep,'atr_on_signal_bar':float(atr[si]),'stop_atr':strategy.stop_atr,'initial_stop_distance':risk,'initial_stop_price':sl,'take_profit_distance':float(atr[si]*strategy.target_atr),'take_profit_price':tp,'time_exit':strategy.time_exit,'planned_exit_bar':iso(df.timestamp[ei+strategy.time_exit-1]) if ei+strategy.time_exit-1<end else '','actual_exit_time':iso(t['exit_time']),'actual_exit_price':xp,'exit_reason':t['reason'],'gross_pnl':float(xp-ep),'cost':0.0,'net_pnl':float(t['pnl']),'gross_R':float((xp-ep)/risk),'net_R':float(t['r'])})
fields=list(py[0]);
with (OUT/'python_trades.csv').open('w',newline='') as f: w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(py)

# Operator-provided MT5 observations. Signal time is inferred as entry bar - 1 H1 bar;
# the EA did not emit signal events in this run.
mt5=[
 {'entry_time':'2024-01-05T21:00:00+00:00','direction':'LONG','volume':2.34,'entry_price':1.09542,'stop':1.09115,'exit_time':'2024-01-05T21:00:40+00:00','exit_price':1.09544,'exit_reason':'TP'},
 {'entry_time':'2024-01-08T17:00:00+00:00','direction':'LONG','volume':4.42,'entry_price':1.09606,'stop':1.09380,'exit_time':'2024-01-08T17:00:20+00:00','exit_price':1.09607,'exit_reason':'TP'},
 {'entry_time':'2024-01-23T08:00:00+00:00','direction':'LONG','volume':5.77,'entry_price':1.09073,'stop':1.08900,'exit_time':'2024-01-23T08:28:40+00:00','exit_price':1.09073,'exit_reason':'TP'},
 {'entry_time':'2024-01-25T09:00:00+00:00','direction':'LONG','volume':5.87,'entry_price':1.08862,'stop':1.08692,'exit_time':'2024-01-25T09:00:40+00:00','exit_price':1.08862,'exit_reason':'TP'},
 {'entry_time':'2024-01-30T15:00:00+00:00','direction':'LONG','volume':4.92,'entry_price':1.08478,'stop':1.08275,'exit_time':'2024-01-30T15:00:20+00:00','exit_price':1.08478,'exit_reason':'TP'},
 {'entry_time':'2024-01-31T15:00:00+00:00','direction':'LONG','volume':4.87,'entry_price':1.08368,'stop':1.08163,'exit_time':'2024-01-31T15:00:40+00:00','exit_price':1.08368,'exit_reason':'TP'},
]
for x in mt5: x['signal_time']=iso(pd.Timestamp(x['entry_time'])-pd.Timedelta(hours=1)); x['time_exit']=strategy.time_exit

def find_py(x):
    return next((p for p in py if p['entry_time']==x['entry_time']),None)
comp=[]
for x in mt5:
    q=find_py(x); base={'python_signal_time':q['signal_bar_time'] if q else '', 'mt5_signal_time':x['signal_time'], 'python_entry_time':q['entry_time'] if q else '', 'mt5_entry_time':x['entry_time'], 'entry_time_match':bool(q and q['entry_time']==x['entry_time']), 'python_direction':q['direction'] if q else '', 'mt5_direction':x['direction'], 'direction_match':bool(q and q['direction']==x['direction']), 'python_entry_price':q['entry_price'] if q else '', 'mt5_entry_price':x['entry_price'], 'entry_price_delta':x['entry_price']-(q['entry_price'] if q else x['entry_price']), 'python_stop':q['initial_stop_price'] if q else '', 'mt5_stop':x['stop'], 'stop_delta':x['stop']-(q['initial_stop_price'] if q else x['stop']), 'python_exit_time':q['actual_exit_time'] if q else '', 'mt5_exit_time':x['exit_time'], 'exit_time_delta':(pd.Timestamp(x['exit_time'])-pd.Timestamp(q['actual_exit_time'])).total_seconds() if q else '', 'python_exit_price':q['actual_exit_price'] if q else '', 'mt5_exit_price':x['exit_price'], 'exit_price_delta':x['exit_price']-(q['actual_exit_price'] if q else x['exit_price']), 'python_exit_reason':q['exit_reason'] if q else '', 'mt5_exit_reason':x['exit_reason'], 'python_time_exit':q['time_exit'] if q else strategy.time_exit, 'mql5_time_exit':strategy.time_exit, 'signal_match':bool(q), 'entry_match':bool(q and q['entry_time']==x['entry_time']), 'stop_match':bool(q and abs(x['stop']-q['initial_stop_price'])<=0.00002), 'exit_match':bool(q and q['exit_reason']==x['exit_reason'] and abs(x['exit_price']-q['actual_exit_price'])<=0.00002), 'classification':'LOGIC_MISMATCH' if not q else ('LOGIC_MISMATCH' if q['exit_reason']!=x['exit_reason'] else ('BROKER_EXECUTION_DIFFERENCE' if abs(x['entry_price']-q['entry_price'])>1e-8 else 'MATCH'))}
    comp.append(base)
cf=list(comp[0]);
with (OUT/'trade_comparison.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=cf);w.writeheader();w.writerows(comp)

risk=[]
for x in mt5:
    dist=abs(x['entry_price']-x['stop']); rawv=100000*.01/(dist/0.00001*1.0); norm=(rawv//.01)*.01; implied=x['volume']*dist/0.00001*1.0
    risk.append({'entry_time':x['entry_time'],'equity':100000,'risk_fraction':.01,'risk_money':1000,'entry':x['entry_price'],'stop':x['stop'],'stop_distance':dist,'tick_size':.00001,'tick_value':1.0,'raw_volume':rawv,'volume_step':.01,'normalized_volume':norm,'actual_mt5_volume':x['volume'],'risk_implied_by_actual_volume':implied,'sizing_difference':x['volume']-norm})
with (OUT/'risk_sizing_comparison.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(risk[0]));w.writeheader();w.writerows(risk)
(OUT/'exit_semantics.md').write_text(f'''# Exit semantics\n\nPython `StrategyDefinition` has `target_atr={strategy.target_atr}` and `time_exit={strategy.time_exit}`. The frozen evaluator computes `target = entry + ATR(signal_bar) * target_atr` for LONG, checks STOP first, then TARGET, then TIME. Time is measured in bars with `held = i - entry_i + 1`; a time exit at `held >= {strategy.time_exit}` uses the close of that bar.\n\nThe pre-fix MQL5 exporter passed `atr*target_atr/stop_atr*stop` as a distance, where `stop` was already `atr*stop_atr`, yielding `target_atr * ATR^2` rather than `target_atr * ATR`. This is the demonstrated root cause of the artificial near-entry TPs and extra MT5 trade.\n\nCurrent MQL5 time-exit handling is documented as a follow-up runtime item: the individual pre-fix EA did not invoke the common position time-exit manager in `OnTick`. This equivalence round fixes the demonstrated TP translation first and records the remaining runtime requirement explicitly.\n''')
(OUT/'data_feed_notes.md').write_text('''# Data/feed notes\n\nThe SQX EURUSD H1 derived dataset contains 528 bars from 2024-01-02 00:00 UTC through 2024-01-31 23:00 UTC, matching the operator-reported MT5 bar count. MT5 OHLC bars/tick export was not available in the Linux workspace, so exact per-bar feed comparison around fills and exits is unresolved. The observed +4e-5 entry differences after the first trade are consistent with Ask/Bid spread and are classified as broker execution/data-feed evidence, not signal logic. Export MT5 H1 OHLC and tick/commission details for the next gate.\n''')
(OUT/'forensics.md').write_text(f'''# Forensics\n\nStrategy `{SID}` canonical hash `{strategy.canonical_hash}` produced {len(py)} Python trades and {len(mt5)} operator-reported MT5 trades. All Python signals in the window are at {', '.join(x['signal_bar_time'] for x in py)} plus the 2024-01-08 16:00 signal that is blocked in the Python position state by the first trade. The first MT5 trade closes at a near-entry TP, allowing the extra 2024-01-08 trade.\n\nThe Python definition explicitly contains `target_atr={strategy.target_atr}`; therefore the near-entry MT5 TP is a translation error, not time_exit reinterpretation. Python uses stop + target + time exit, in that priority. Costs and feed differences are secondary to this logical mismatch.\n''')
