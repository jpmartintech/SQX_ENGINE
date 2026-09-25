from dataclasses import dataclass, asdict
import hashlib,json
import numpy as np
@dataclass(frozen=True)
class PortfolioConstraints:
 max_strategies:int=10; max_pair_correlation:float=.8; max_per_market:int|None=None; max_per_timeframe:int|None=None; max_per_cluster:int=1; max_xau_fraction:float|None=None; max_long_fraction:float|None=None; max_short_fraction:float|None=None
@dataclass(frozen=True)
class PortfolioRequest:
 strategy_ids:tuple; weighting:str='EQUAL_WEIGHT'; risk_level:float=1.0; constraints:PortfolioConstraints=PortfolioConstraints()
def portfolio_hash(req):
 d={'strategy_ids':sorted(req.strategy_ids),'weighting':req.weighting,'risk_level':req.risk_level,'constraints':asdict(req.constraints)}
 return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest()
class PortfolioEngine:
 def __init__(self, returns, metadata, timestamps=None):
  self.returns=np.asarray(returns,float); self.metadata=metadata; self.timestamps=timestamps
 def weights(self, ids, method='EQUAL_WEIGHT'):
  idx=[self.metadata['index'][i] for i in ids]; x=self.returns[:,idx]
  if method=='EQUAL_RISK':
   v=np.std(x,axis=0); w=1/np.maximum(v,1e-12); return w/w.sum()
  if method=='INVERSE_VOL':
   v=np.std(x,axis=0); w=1/np.maximum(v,1e-12); return w/w.sum()
  return np.ones(len(ids))/max(1,len(ids))
 def validate(self,ids,c):
  if not ids or len(ids)>c.max_strategies:return False,'SIZE'
  xs=[self.metadata['rows'][i] for i in ids];
  if c.max_per_market and max([sum(x['market']==m for x in xs) for m in set(x['market'] for x in xs)])>c.max_per_market:return False,'MARKET_CONCENTRATION'
  if c.max_per_timeframe and max([sum(x['timeframe']==m for x in xs) for m in set(x['timeframe'] for x in xs)])>c.max_per_timeframe:return False,'TIMEFRAME_CONCENTRATION'
  if c.max_per_cluster and max([sum(x['cluster']==m for x in xs) for m in set(x['cluster'] for x in xs)])>c.max_per_cluster:return False,'BEHAVIORAL_CLUSTER'
  if c.max_xau_fraction and sum(x['market']=='XAUUSD' for x in xs)/len(xs)>c.max_xau_fraction:return False,'XAU_CONCENTRATION'
  return True,''
 def evaluate(self,ids,weighting='EQUAL_WEIGHT',risk_level=1.0):
  idx=[self.metadata['index'][i] for i in ids]; w=self.weights(ids,weighting)*risk_level; stream=self.returns[:,idx]@w; total=float(stream.sum()); vol=float(stream.std()); sharpe=float(stream.mean()/vol*np.sqrt(252)) if vol else 0.; curve=np.cumsum(stream); peak=np.maximum.accumulate(curve); dd=float(np.max(peak-curve)) if len(curve) else 0.; wins=stream[stream>0].sum(); losses=stream[stream<0].sum(); pf=float(wins/abs(losses)) if losses else float('inf')
  return {'strategy_ids':list(ids),'weights':dict(zip(ids,w.tolist())),'net_return':total,'volatility':vol,'sharpe':sharpe,'sortino':float(stream.mean()/(stream[stream<0].std() or 1e-12)*np.sqrt(252)),'max_drawdown':dd,'profit_factor':pf,'trade_count':int(np.count_nonzero(stream)),'average_correlation':0.,'max_pair_correlation':0.,'stream':stream}
