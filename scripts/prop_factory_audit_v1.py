from pathlib import Path
import argparse, json
from sqx_engine.prop_factory.audit import run_prop_audit

def main():
    p=argparse.ArgumentParser(); p.add_argument('--profile',default='FTMO_2STEP_V1'); p.add_argument('--seed',type=int,default=1301); p.add_argument('--random-count',type=int,default=120); p.add_argument('--probe-count',type=int,default=24)
    a=p.parse_args()
    if a.profile != 'FTMO_2STEP_V1': raise SystemExit('only FTMO_2STEP_V1 is implemented')
    print(json.dumps(run_prop_audit(Path(__file__).resolve().parents[1],a.seed,a.random_count,a.probe_count),indent=2))
if __name__=='__main__': main()
