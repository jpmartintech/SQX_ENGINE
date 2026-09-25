"""Independent quote-scale checks and deliberate x10/x100 error rejection."""
from pathlib import Path
from copy import deepcopy
import yaml
from sqx_engine.production import atomic_json
ROOT=Path(__file__).resolve().parents[2]
EXPECTED={'EURUSD':(.0001,.00001,.00008,.00002),'GBPUSD':(.0001,.00001,.00010,.00006),'NZDUSD':(.0001,.00001,.00020,.00010),'USDCAD':(.0001,.00001,.00015,.00010),'USDCHF':(.0001,.00001,.00015,.00010),'USDJPY':(.01,.001,.008,.004),'XAUUSD':(.01,.01,.30,.10)}
def validate(p):
 expected=EXPECTED[p['market']]
 for key,value in zip(['pip_size','tick_size','spread','slippage'],expected):
  if p[key]!=value:raise ValueError(f'UNIT_OR_COST_MISMATCH: {p["market"]} {key}')
 return True
if __name__=='__main__':
 profiles=yaml.safe_load((ROOT/'configs/execution_profiles/production_v1.yaml').read_text())['profiles'];rejected=0
 for p in profiles.values():
  validate(p)
  for key in ['pip_size','tick_size','spread','slippage']:
   for factor in [.01,.1,10,100]:
    wrong=deepcopy(p);wrong[key]*=factor
    try:validate(wrong)
    except ValueError:rejected+=1
    else:raise AssertionError('Failed to reject scale mutation')
 atomic_json(ROOT/'runs/reports/production_02/unit_checks.json',{'status':'PASS','profiles_checked':len(profiles),'deliberate_scale_errors_rejected':rejected,'expected_quote_scale':EXPECTED})
 print('Units PASS;',rejected,'deliberate errors rejected')
