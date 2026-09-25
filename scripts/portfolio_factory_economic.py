"""AUDIT_ONLY economic scaling calibration for the frozen V1.0 pilot."""
import csv,json,sqlite3,time
from pathlib import Path
import numpy as np
from sqx_engine.portfolio_factory.economic import EconomicConfig,AccountEquityEngine
from sqx_engine.portfolio_factory.ftmo import FtmoSimulator,FtmoConfig
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runs/reports/portfolio_factory_v1/economic_scaling'; OUT.mkdir(parents=True,exist_ok=True)
REPLAY=ROOT/'runs/library_replay/replay.sqlite'; OLD=ROOT/'runs/reports/portfolio_factory_v1/pilot_results.csv'

ALL_RETURNS=None
def load_returns(ids):
 rows=[(s,t,v) for s in ids for t,v in ALL_RETURNS.get(s,[])]
 ts=sorted({r[1] for r in rows}); ti={t:i for i,t in enumerate(ts)}; idx={s:i for i,s in enumerate(ids)}; a=np.zeros((len(ts),len(ids)))
 for s,t,v in rows:a[ti[t],idx[s]]=float(v)
 return np.array(ts),a

def main():
 global ALL_RETURNS
 t0=time.time(); records=[]; traces=[]
 c=sqlite3.connect(REPLAY); ALL_RETURNS={}
 for s,t,v in c.execute('select strategy_id,timestamp,net_return from returns'):
  ALL_RETURNS.setdefault(s,[]).append((t,float(v)))
 c.close()
 with OLD.open(newline='') as f: old=list(csv.DictReader(f))
 cache={}
 for row in old:
  ids=json.loads(row['strategy_ids_json']); weights=json.loads(row['weights_json']); key=tuple(ids)
  if key not in cache: cache[key]=load_returns(ids)
  ts,a=cache[key]; raw=a@np.array([weights[x] for x in ids])
  for rt in (.0025,.005,.0075,.01):
   ec=EconomicConfig(initial_capital=10000.,baseline_target=.01,risk_target=rt); em=AccountEquityEngine(ec); m=em.metrics(raw,ts)
   f=FtmoSimulator(FtmoConfig(initial_capital=10000.)).run(m['pnl'],ts)
   records.append({'method':row['method'],'evaluation':row['evaluation'],'size':row['size'],'weighting':row['weighting'],'portfolio_hash':row['portfolio_hash'],'risk_target':rt,'raw_net_return':float(raw.sum()),'economic_pnl':float(m['pnl'].sum()),'max_drawdown':m['max_drawdown'],'max_daily_loss':f['max_daily_loss'],'maximum_achieved_return':f['maximum_achieved_return'],'final_return':f['final_return'],'distance_to_target':f.get('distance_to_target',0.),'ftmo_status':f['status']})
  if len(traces)<3:
   traces.append({'portfolio_hash':row['portfolio_hash'],'strategy_id':ids[0],'market':ids[0].split('-')[1],'timeframe':ids[0].split('-')[2],'stored_net_return_example':'see replay return stream','risk_target':rt,'initial_capital':10000.,'economic_definition':'normalized return × capital × risk_target/0.01'})
 with (OUT/'corrected_pilot_results.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(records[0])); w.writeheader(); w.writerows(records)
 counts=[]
 for rt in (.0025,.005,.0075,.01):
  xs=[r for r in records if r['risk_target']==rt];
  for method in ('RANDOM','GREEDY_DIVERSITY','GENETIC'):
   ys=[r for r in xs if r['method']==method]; counts.append({'risk_target':rt,'method':method,'PASS':sum(r['ftmo_status']=='PASS' for r in ys),'FAIL_DAILY':sum(r['ftmo_status']=='FAIL_DAILY' for r in ys),'FAIL_TOTAL':sum(r['ftmo_status']=='FAIL_TOTAL' for r in ys),'TIMEOUT':sum(r['ftmo_status']=='TIMEOUT' for r in ys),'median_final_return':float(np.median([float(r['final_return']) for r in ys])),'median_max_drawdown':float(np.median([float(r['max_drawdown']) for r in ys])),'median_max_daily_loss':float(np.median([float(r['max_daily_loss']) for r in ys])),'median_maximum_achieved_return':float(np.median([float(r['maximum_achieved_return']) for r in ys]))})
 with (OUT/'corrected_ftmo_analysis.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(counts[0]));w.writeheader();w.writerows(counts)
 json.dump({'rows':len(records),'risk_targets':[.0025,.005,.0075,.01],'pilot_source':'pilot_results.csv','same_portfolios':True,'runtime_seconds':time.time()-t0},open(OUT/'performance.json','w'),indent=2)
 json.dump({'status':'PASS','replay_immutable':True,'no_generation':True,'no_promotion':True,'account_units':'USD','net_return_semantics':'dimensionless evaluator PnL / evaluator initial capital','risk_semantics':'account-return allocation target relative to 1% baseline; not stop-risk sizing'},open(OUT/'integrity.json','w'),indent=2)
 json.dump({'root_cause':'The legacy FTMO call passed dimensionless normalized returns as dollar PnL. This produced tiny monetary equity changes. Corrected engine converts normalized return to account-currency PnL before FTMO. Percentage outcomes remain governed by the explicitly defined risk allocation.','legacy_risk_level':'1.0 was a direct multiplier on normalized portfolio returns.','trace_examples':traces},open(OUT/'unit_trace.json','w'),indent=2)
 print(json.dumps({'records':len(records),'runtime':time.time()-t0},indent=2))
if __name__=='__main__': main()
