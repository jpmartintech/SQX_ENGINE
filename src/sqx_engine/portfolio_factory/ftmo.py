from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np
@dataclass(frozen=True)
class FtmoConfig:
 initial_capital:float=10000.; profit_target:float=.10; max_daily_loss:float=.05; max_total_loss:float=.10; minimum_trading_days:int=4; max_days:Optional[int]=30; timezone:str='UTC'; max_calendar_days:Optional[int]=None
class FtmoSimulator:
 def __init__(self,cfg=FtmoConfig()): self.cfg=cfg
 def run(self,stream,timestamps=None):
  if timestamps is None: timestamps=pd.date_range('2000-01-01',periods=len(stream),freq='15min',tz='UTC')
  # ``stream`` is explicitly economic PnL in account currency.  The old
  # caller passed normalized returns; callers must use AccountEquityEngine.
  di=pd.DatetimeIndex(timestamps)
  if di.tz is None: di=di.tz_localize(self.cfg.timezone)
  else: di=di.tz_convert(self.cfg.timezone)
  start=di.min() if len(di) else None
  cutoff=(start+pd.Timedelta(days=self.cfg.max_calendar_days-1)) if start is not None and self.cfg.max_calendar_days is not None else None
  mask=np.asarray(di <= cutoff) if cutoff is not None else np.ones(len(di),dtype=bool)
  s=pd.Series(np.asarray(stream)[mask],index=di[mask]).groupby(di[mask].date).sum(); eq=self.cfg.initial_capital; peak=self.cfg.initial_capital; days=0; max_daily=0.; max_total=0.; max_return=0.
  for day,pnl in s.items():
   days+=1; daily=float(pnl)/self.cfg.initial_capital; eq+=float(pnl); peak=max(peak,eq); total=eq/self.cfg.initial_capital-1; max_daily=max(max_daily,-daily); max_total=max(max_total,1-eq/self.cfg.initial_capital); max_return=max(max_return,total)
   base={'days':days,'return':total,'final_return':total,'max_daily_loss':max_daily,'max_total_drawdown':max_total,'maximum_achieved_return':max_return}
   if daily < -self.cfg.max_daily_loss:return dict(status='FAIL_DAILY',**base)
   if total < -self.cfg.max_total_loss:return dict(status='FAIL_TOTAL',**base)
   if total >= self.cfg.profit_target and days>=self.cfg.minimum_trading_days:return dict(status='PASS',**base)
   if self.cfg.max_calendar_days is None and self.cfg.max_days is not None and days>=self.cfg.max_days:break
  total=eq/self.cfg.initial_capital-1
  reached_horizon = bool(cutoff is not None and len(di) and di.max() >= cutoff)
  status='TIMEOUT' if reached_horizon or (self.cfg.max_calendar_days is None and self.cfg.max_days is not None and days>=self.cfg.max_days) else 'DATA_END'
  return {'status':status,'days':days,'return':total,'final_return':total,'max_daily_loss':max_daily,'max_total_drawdown':max_total,'maximum_achieved_return':max_return,'distance_to_target':self.cfg.profit_target-max_return,'days_observed':int((di[mask].max()-start).days+1) if len(di) and start is not None else 0}
