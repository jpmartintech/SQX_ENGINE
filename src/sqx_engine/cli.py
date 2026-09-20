import argparse, json
from .config import EngineConfig
from .engine import StrategyFactory

def main():
    p=argparse.ArgumentParser(prog="sqx"); sub=p.add_subparsers(dest="command",required=True); run=sub.add_parser("run"); run.add_argument("config")
    args=p.parse_args()
    if args.command=="run": print(json.dumps(StrategyFactory(EngineConfig.from_yaml(args.config)).run(),indent=2,default=str))

if __name__ == "__main__":
    main()
