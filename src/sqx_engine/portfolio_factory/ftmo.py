from dataclasses import dataclass
import pandas as pd
@dataclass(frozen=True)
class FtmoConfig:
 initial_capital:float=10000.; profit_target:float=.10; max_daily_loss:float=.05; max_total_loss:float=.10; minimum_trading_days:int=4; max_days:int=30; timezone:str='UTC'
class FtmoSimulator:
 def __init__(self,cfg=FtmoConfig()): self.cfg=cfg
 def run(self,stream,timestamps=None):
  if timestamps is None: timestamps=pd.date_range('2000-01-01',periods=len(stream),freq='15min',tz='UTC')
  # ``stream`` is explicitly economic PnL in account currency.  The old
  # caller passed normalized returns; callers must use AccountEquityEngine.
  s=pd.Series(stream,index=pd.DatetimeIndex(timestamps)).groupby(pd.DatetimeIndex(timestamps).date).sum(); eq=self.cfg.initial_capital; peak=self.cfg.initial_capital; days=0; max_daily=0.; max_total=0.; max_return=0.
  for day,pnl in s.items():
   days+=1; daily=float(pnl)/self.cfg.initial_capital; eq+=float(pnl); peak=max(peak,eq); total=eq/self.cfg.initial_capital-1; max_daily=max(max_daily,-daily); max_total=max(max_total,1-eq/self.cfg.initial_capital); max_return=max(max_return,total)
   base={'days':days,'return':total,'final_return':total,'max_daily_loss':max_daily,'max_total_drawdown':max_total,'maximum_achieved_return':max_return}
   if daily < -self.cfg.max_daily_loss:return dict(status='FAIL_DAILY',**base)
   if total < -self.cfg.max_total_loss:return dict(status='FAIL_TOTAL',**base)
   if total >= self.cfg.profit_target and days>=self.cfg.minimum_trading_days:return dict(status='PASS',**base)
   if days>=self.cfg.max_days:break
  total=eq/self.cfg.initial_capital-1
  return {'status':'TIMEOUT','days':days,'return':total,'final_return':total,'max_daily_loss':max_daily,'max_total_drawdown':max_total,'maximum_achieved_return':max_return,'distance_to_target':self.cfg.profit_target-max_return}
