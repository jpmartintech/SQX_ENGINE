import argparse, json
from .config import EngineConfig
from .engine import StrategyFactory
from .store import StrategyStore

def main():
    p=argparse.ArgumentParser(prog="sqx"); sub=p.add_subparsers(dest="command",required=True); run=sub.add_parser("run"); run.add_argument("config"); run.add_argument("--resume",action="store_true")
    strategies=sub.add_parser("strategies"); strategy_sub=strategies.add_subparsers(dest="strategy_command",required=True); show=strategy_sub.add_parser("show"); show.add_argument("strategy_id"); show.add_argument("--db",default="runs/sqx_engine.sqlite")
    args=p.parse_args()
    if args.command=="run": print(json.dumps(StrategyFactory(EngineConfig.from_yaml(args.config)).run(resume=args.resume),indent=2,default=str))
    elif args.command=="strategies" and args.strategy_command=="show":
        store=StrategyStore(args.db); print(json.dumps(store.get_strategy(args.strategy_id),indent=2,default=str)); store.close()

if __name__ == "__main__":
    main()
