"""Operational input freeze. No trading/engine changes; no OOS-driven calibration."""
from pathlib import Path
from decimal import Decimal
from collections import Counter
import json,copy,sqlite3
import numpy as np
import yaml
from sqx_engine.production import ProductionFactory,atomic_json
from sqx_engine.config import EngineConfig
from sqx_engine.data.split import file_sha256,audit_dataset,partition_dataset
from sqx_engine.data.catalog import MARKETS
from sqx_engine.features.engine import prepare_features
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition,Predicate
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/production_02'; VERSION='PRODUCTION_EXECUTION_V1'
SRC=Path('/home/xaume/proyectos/sqx_lite/market_profiles/profiles.yaml')
def write_frozen(path,value):
 text=yaml.safe_dump(value,sort_keys=False)
 if path.exists(): assert path.read_text()==text, f'Frozen input differs: {path}'
 else:path.write_text(text)
def main():
 historical=yaml.safe_load(SRC.read_text()); profiles={}; rows=[]
 snapshot={m:historical[m] for m in MARKETS}
 write_frozen(ROOT/'configs/execution_profiles/historical_source.yaml',snapshot)
 for m in MARKETS:
  h=historical[m]; pip=Decimal(str(h['pip'])); fee=Decimal(str(h['fee_pips']))*pip; slip=2*Decimal(str(h['slippage_pips']))*pip
  if m=='EURUSD':fee=Decimal('0.00008');slip=Decimal('0.00002')
  for tf in ['M15','H1','H4']:
   p={'market':m,'timeframe':tf,'spread':float(fee),'slippage':float(slip),'units':'quote-price units per completed trade','pip_size':float(pip),'tick_size':h['tick_size'],'source':str(SRC) if m!='EURUSD' else 'configs/production_01_ready.yaml','source_sha256':file_sha256(SRC) if m!='EURUSD' else file_sha256(ROOT/'configs/production_01_ready.yaml'),'rationale':'Historical simulation assumption: round-trip fee_pips*pip deducted through spread; 2*per-side slippage_pips*pip deducted once. Not a broker quote or measured fill distribution.' if m!='EURUSD' else 'Unchanged V1.8 EURUSD round-trip price-unit cost, identical across TF; no timeframe scaling. H1 jobs remain Production 01 and are excluded.','commission_model':'No separate commission field supported; historical aggregate friction is represented through spread.','status':'APPROVED','version':VERSION,'initial_capital':10000}
   assert p['spread']>0 and p['slippage']>0
   assert Decimal(str(p['spread']))==fee and Decimal(str(p['slippage']))==slip
   # The independent historical formula rejects decimal-point and side-count mistakes.
   for factor in [Decimal('0.01'),Decimal('0.1'),Decimal('10'),Decimal('100')]:assert Decimal(str(p['spread']))*factor!=fee
   profiles[f'{m}_{tf}']=p;rows.append(p)
 manifest={'execution_profile_version':VERSION,'frozen_before_strategy_results':True,'cost_model':'net_pnl = gross_pnl - (spread + slippage) * cost_multiplier, once per trade','source_semantics_path':'/home/xaume/proyectos/sqx_lite/market_profiles/__init__.py','source_semantics_sha256':file_sha256('/home/xaume/proyectos/sqx_lite/market_profiles/__init__.py'),'approval_basis':'Existing explicit historical configs, with conservative preservation of both slippage sides; no new broker claims or result-driven fitting.','profiles':profiles}
 path=ROOT/'configs/execution_profiles/production_v1.yaml';write_frozen(path,manifest)
 atomic_json(OUT/'execution_profiles.json',manifest)
 lines=['# PRODUCTION_EXECUTION_V1 — frozen assumptions','','V1.8 deducts costs once per completed trade. No separate commission parameter exists. The spread field below represents the historical aggregate round-trip friction; it is not asserted to be a measured bid/ask spread. Slippage for new markets preserves both historical execution sides. EURUSD remains at its V1.8 baseline. No costs are scaled by timeframe.','','| Market | TF | Spread | Slippage | Commission | Unit | Source | Status |','|---|---|---:|---:|---|---|---|---|']
 for p in rows:lines.append(f"| {p['market']} | {p['timeframe']} | {p['spread']} | {p['slippage']} | no separate field | quote price/trade | {'V1.8 baseline' if p['market']=='EURUSD' else 'historical sqx_lite profile'} | APPROVED |")
 (OUT/'execution_profiles.md').write_text('\n'.join(lines)+'\n')
 base=yaml.safe_load((ROOT/'configs/production_01_base.yaml').read_text());base['production_batch']='PRODUCTION_02';base['execution_profile_version']=VERSION;base['execution_profile_manifest_sha256']=file_sha256(path)
 write_frozen(ROOT/'configs/production_02_base.yaml',base)
 batch=yaml.safe_load((ROOT/'configs/production_01_matrix.yaml').read_text());batch.update(batch_name='PRODUCTION_02',base_config='configs/production_02_base.yaml',execution_profile_version=VERSION,execution_profiles={k:v for k,v in profiles.items() if k!='EURUSD_H1'},output_root='runs/production/PRODUCTION_02',resource_guards={'max_memory_gb':20})
 batch['excluded_completed']=[{'market':'EURUSD','timeframe':'H1','seed':s} for s in [1301,1302,1303]]
 write_frozen(ROOT/'configs/production_02_matrix.yaml',batch)
 factory=ProductionFactory(ROOT)
 try:
  alljobs=factory.plan(batch); jobs=[j for j in alljobs if not(j.market=='EURUSD' and j.timeframe=='H1')]; assert len(jobs)==60
  coverage={}; checks=[]; plans=[]; configs=[]
  for j in jobs:
   key=(j.market,j.timeframe)
   if key not in coverage:
    frame,audit=audit_dataset(ROOT/j.dataset['path']); split=partition_dataset(EngineConfig(j.config),frame);coverage[key]=split.manifest()
    old=next(r for r in json.loads((ROOT/'runs/reports/production_01/plan.json').read_text())['jobs'] if (r['market'],r['timeframe'])==key)
    assert old['dataset_sha256']==audit['sha256'] and not old['issues'] and old['splits']==coverage[key]
    # Fixed diagnostic, Development only. Costs cannot change signals or exits.
    df=split.development_df.iloc[:2048].copy();features=prepare_features(df,'v1.7');p=profiles[f'{j.market}_{j.timeframe}']
    for direction in ['LONG','SHORT']:
     strategy=StrategyDefinition(j.market,j.timeframe,direction,(Predicate('rsi_14','>',50),),grammar_version='v1.7')
     answers={}
     for engine in ['python','numba']:
      zero=FastEvaluator(df,features,spread=0,slippage=0,engine=engine).evaluate(strategy)
      paid=FastEvaluator(df,features,spread=p['spread'],slippage=p['slippage'],engine=engine).evaluate(strategy)
      assert zero.trade_count==paid.trade_count and paid.trade_count>0
      np.testing.assert_allclose(np.array(zero.trade_returns)-np.array(paid.trade_returns),p['spread']+p['slippage'],rtol=1e-9,atol=1e-10)
      assert [(t['entry_time'],t['exit_time'],t['reason']) for t in zero.trades]==[(t['entry_time'],t['exit_time'],t['reason']) for t in paid.trades]
      assert all(np.isfinite(getattr(paid,k)) for k in ['net_profit','expectancy','sharpe','max_drawdown'])
      answers[engine]=paid.trade_returns
     np.testing.assert_allclose(answers['python'],answers['numba'],rtol=1e-9,atol=1e-10)
    checks.append({'market':j.market,'timeframe':j.timeframe,'status':'PASS','expected_roundtrip_cost':p['spread']+p['slippage'],'scope':'first 2048 Development bars; fixed RSI rule; LONG and SHORT; Python/Numba; no Validation/OOS read for cost selection'})
   assert j.status=='PENDING'
   one=copy.deepcopy(batch);one.update(markets=[j.market],timeframes=[j.timeframe],seeds=[j.seed]);one.pop('excluded_completed',None)
   cfg=ROOT/f'configs/production_02_{j.market.lower()}_{j.timeframe.lower()}_{j.seed}.yaml';write_frozen(cfg,one)
   configs.append(str(cfg.relative_to(ROOT)))
   plans.append({'job_id':j.job_id,'market':j.market,'timeframe':j.timeframe,'seed':j.seed,'dataset_sha256':j.dataset['sha256'],'splits':coverage[key],'execution_profile_version':VERSION,'spread':j.config['backtest']['spread'],'slippage':j.config['backtest']['slippage'],'status':'READY','config':str(cfg.relative_to(ROOT)),'directory':j.directory,'canary':j.seed==1301 and ((j.market=='EURUSD' and j.timeframe in ['M15','H4']) or (j.market!='EURUSD' and j.timeframe=='H1'))})
  atomic_json(OUT/'cost_checks.json',checks)
  plan={'batch':'PRODUCTION_02','requested_remaining':60,'ready':60,'blocked':0,'already_complete_excluded':3,'planned_evaluations':15000000,'manifest_sha256':file_sha256(path),'production_policy':batch['temporal_policy'],'jobs':plans}
  atomic_json(OUT/'plan.json',plan)
  lines=['# PRODUCTION_02 plan','','60 READY jobs; 15,000,000 evaluations. Three EURUSD H1 Production 01 jobs excluded. Eight canaries run first and count as final jobs.','','| Market | TF | Seed | Dev bars | Val bars | OOS bars | Spread | Slippage | Status |','|---|---|---:|---:|---:|---:|---:|---:|---|']
  for r in plans:lines.append(f"| {r['market']} | {r['timeframe']} | {r['seed']} | {r['splits']['development']['bars']} | {r['splits']['validation']['bars']} | {r['splits']['oos']['bars']} | {r['spread']} | {r['slippage']} | READY |")
  (OUT/'plan.md').write_text('\n'.join(lines)+'\n')
  with sqlite3.connect(ROOT/'library/strategies.sqlite') as db:
   before={'total':db.execute('SELECT count(*) FROM strategies').fetchone()[0],'observations':db.execute('SELECT count(*) FROM observations').fetchone()[0],'hashes':[r[0] for r in db.execute('SELECT canonical_hash FROM strategies ORDER BY canonical_hash')]}
  if not (OUT/'library_before.json').exists():atomic_json(OUT/'library_before.json',before)
  print('FROZEN: 20 new approved profiles + EURUSD H1 baseline; 60 READY; cost checks PASS',flush=True)
 finally:factory.close()
if __name__=='__main__':main()
