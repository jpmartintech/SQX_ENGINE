import argparse, json
from .config import EngineConfig
from .engine import StrategyFactory
from .store import StrategyStore

def main():
    p=argparse.ArgumentParser(prog="sqx"); sub=p.add_subparsers(dest="command",required=True); run=sub.add_parser("run"); run.add_argument("config"); run.add_argument("--resume",action="store_true"); run.add_argument("--workers",default=None, help="worker count or auto"); run.add_argument("--engine",default=None, choices=("auto", "python", "numba"))
    validate = sub.add_parser("validate"); validate.add_argument("config")
    strategies=sub.add_parser("strategies"); strategy_sub=strategies.add_subparsers(dest="strategy_command",required=True); show=strategy_sub.add_parser("show"); show.add_argument("strategy_id"); show.add_argument("--db",default="runs/sqx_engine.sqlite")
    benchmark = sub.add_parser('benchmark'); benchmark.add_argument('version', choices=['v1.7']); benchmark.add_argument('--mode', choices=['fast','audit','full'], default='fast'); benchmark.add_argument('--output', default='runs/benchmarks/v18_full')
    data = sub.add_parser('data'); data.add_argument('action', choices=['scan','list']); data.add_argument('--no-derive',action='store_true')
    library = sub.add_parser('library'); library.add_argument('action',choices=['stats','list','import-v17']); library.add_argument('--db',default='library/strategies.sqlite'); library.add_argument('--market'); library.add_argument('--timeframe'); library.add_argument('--family'); library.add_argument('--limit',type=int,default=100); library.add_argument('--include-analysis',action='store_true')
    production = sub.add_parser('production'); production.add_argument('action',choices=['plan','run','resume','status']); production.add_argument('config',nargs='?'); production.add_argument('--jobs-db',default='runs/production/jobs.sqlite'); production.add_argument('--library-db',default='library/strategies.sqlite')
    factory = sub.add_parser('factory'); factory.add_argument('action',choices=['status'])
    prop = sub.add_parser('prop'); prop_sub = prop.add_subparsers(dest='prop_action', required=True)
    audit = prop_sub.add_parser('audit'); audit.add_argument('--profile', default='FTMO_2STEP_V1'); audit.add_argument('--seed', type=int, default=1301); audit.add_argument('--random-count', type=int, default=120); audit.add_argument('--probe-count', type=int, default=24)
    discover = prop_sub.add_parser('discover'); discover.add_argument('--profile', default='FTMO_2STEP_V1'); discover.add_argument('--phase', choices=('challenge','verification'), required=True)
    deployment = sub.add_parser('deployment'); deployment.add_argument('deployment_args', nargs=argparse.REMAINDER)
    args=p.parse_args()
    if args.command=="run":
        config = EngineConfig.from_yaml(args.config)
        if args.engine is not None:
            config.raw["engine"] = args.engine
        print(json.dumps(StrategyFactory(config).run(resume=args.resume, workers=args.workers),indent=2,default=str))
    elif args.command=="validate":
        from .validation import ValidationFactory, json_safe
        print(json.dumps(json_safe(ValidationFactory(EngineConfig.from_yaml(args.config)).run()), indent=2, allow_nan=False))
    elif args.command == 'deployment':
        from .deployment.cli import main as deployment_main
        deployment_main(args.deployment_args)
    elif args.command in {'benchmark','data','library','production','factory','prop'}:
        from .operations import dispatch
        result = dispatch(args)
        print(json.dumps(result,indent=2,default=str))
        if result.get('status') == 'FAIL': raise SystemExit(1)
    elif args.command=="strategies" and args.strategy_command=="show":
        store=StrategyStore(args.db); print(json.dumps(store.get_strategy(args.strategy_id),indent=2,default=str)); store.close()

if __name__ == "__main__":
    main()
