from dataclasses import dataclass
import pandas as pd
@dataclass(frozen=True)
class FtmoConfig:
 initial_capital:float=10000.; profit_target:float=.10; max_daily_loss:float=.05; max_total_loss:float=.10; minimum_trading_days:int=4; max_days:int=30; timezone:str='UTC'
class FtmoSimulator:
 def __init__(self,cfg=FtmoConfig()): self.cfg=cfg
 def run(self,stream,timestamps=None):
  if timestamps is None: timestamps=pd.date_range('2000-01-01',periods=len(stream),freq='15min',tz='UTC')
  s=pd.Series(stream,index=pd.DatetimeIndex(timestamps)).groupby(pd.DatetimeIndex(timestamps).date).sum(); eq=self.cfg.initial_capital; peak=self.cfg.initial_capital; days=0
  for day,pnl in s.items():
   days+=1; daily=float(pnl)/self.cfg.initial_capital; eq+=float(pnl); peak=max(peak,eq)
   if daily < -self.cfg.max_daily_loss:return {'status':'FAIL_DAILY','days':days,'return':eq/self.cfg.initial_capital-1}
   if eq/self.cfg.initial_capital-1 < -self.cfg.max_total_loss:return {'status':'FAIL_TOTAL','days':days,'return':eq/self.cfg.initial_capital-1}
   if eq/self.cfg.initial_capital-1 >= self.cfg.profit_target and days>=self.cfg.minimum_trading_days:return {'status':'PASS','days':days,'return':eq/self.cfg.initial_capital-1}
   if days>=self.cfg.max_days:break
  return {'status':'TIMEOUT','days':days,'return':eq/self.cfg.initial_capital-1}
