"""Operational downstream production layer for PROP portfolios."""
from dataclasses import dataclass,asdict
from enum import Enum
import hashlib,json,sqlite3
class Decision(str,Enum): ACCEPT='ACCEPT_FULL'; RESIZE='ACCEPT_REDUCED'; REJECT='REJECT_RISK_LIMIT'
@dataclass(frozen=True)
class PropProfile:
 name:str='GENERIC_PROP_V1'; target_pct:float=.10; daily_loss_pct:float=.05; max_loss_pct:float=.10; min_days:int=4; max_calendar_days:int|None=None; mode:str='REALIZED_ONLY'
@dataclass(frozen=True)
class AccountSpec:
 initial_equity:float=100000.; currency:str='USD'
@dataclass(frozen=True)
class MarketSpec:
 market:str; asset_class:str='FOREX'; currency:str='USD'; tick_size:float=0.; tick_value:float=0.; point_value:float=0.; contract_multiplier:float=1.; lot_step:float=0.01; minimum_quantity:float=0.01; margin_model:str='CONFIG_REQUIRED'; execution_model:str='CONFIG_REQUIRED'
@dataclass(frozen=True)
class ExecutionFeasibility:
 status:str='PASS'; reason:str='FOREX relative sizing; broker constraints configurable'; quantity:float|None=None
class PortfolioRiskManager:
 def __init__(self,account:AccountSpec,budget:float,max_open_risk:float): self.account=account;self.budget=budget;self.max_open=max_open_risk
 def allocate(self,requested:float,current_open:float=0.):
  available=min(self.budget-current_open,self.max_open-current_open)
  if requested<=0:return {'decision':Decision.REJECT.value,'allocated':0.,'reason':'INVALID_REQUEST'}
  if available<=0:return {'decision':Decision.REJECT.value,'allocated':0.,'reason':'RISK_LIMIT'}
  if requested<=available:return {'decision':Decision.ACCEPT.value,'allocated':requested,'reason':'WITHIN_BUDGET'}
  return {'decision':Decision.RESIZE.value,'allocated':available,'reason':'REDUCED_TO_AVAILABLE_CAPACITY'}

def portfolio_identity(strategy_ids,weights,risk_policy,prop_profile):
 d={'strategy_ids':sorted(strategy_ids),'weights':weights,'risk_policy':risk_policy,'prop_profile':asdict(prop_profile) if hasattr(prop_profile,'__dataclass_fields__') else prop_profile}
 h=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest();return 'SQX-PROP-'+h[:12].upper(),h

def init_library(path):
 c=sqlite3.connect(path);c.execute('''create table if not exists portfolios(portfolio_id text primary key,portfolio_hash text unique,strategy_ids text,weights text,risk_policy text,risk_budget real,prop_profile text,creation_method text,seed integer,metrics text,stress_metrics text,status text,created_at text,updated_at text)''');c.commit();return c
