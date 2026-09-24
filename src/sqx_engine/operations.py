"""CLI operations, kept outside trading modules."""
from pathlib import Path
from collections import Counter

from .benchmark import fast_regression, audit_golden, full_regression, manifest
from .config import EngineConfig
from .data.catalog import DataCatalog
from .data.split import file_sha256
from .library import StrategyLibrary
from .production import ProductionFactory, VERSION, atomic_json


def dispatch(args):
    root = EngineConfig({}).project_root
    if args.command == 'benchmark':
        if args.mode == 'fast': result = fast_regression(root)
        elif args.mode == 'audit': result = audit_golden(root)
        else: result = full_regression(root,root/args.output)
        atomic_json(root/f'runs/reports/v18/golden_{args.mode}.json',result)
        return result
    if args.command == 'data':
        catalog = DataCatalog(root)
        if args.action == 'scan' or not catalog.records: catalog.scan(derive=not args.no_derive)
        return {'datasets':catalog.records,'counts':dict(Counter(r['status'] for r in catalog.records))}
    if args.command == 'library':
        library = StrategyLibrary(root/args.db)
        try:
            if args.action == 'stats': return library.stats(args.include_analysis)
            if args.action == 'list': return {'strategies':library.list(args.market,args.timeframe,args.family,args.include_analysis,args.limit)}
            m=manifest(root)
            for key,sha in [('source_database','source_database_sha256'),('validation_database','validation_database_sha256')]:
                if file_sha256(root/m[key]) != m[sha]: raise ValueError('Golden source has changed')
            result=library.promote(root/m['source_database'],root/m['validation_database'],m['validation_run_id'],
                                   job_id='LEGACY_V1_7_GOLDEN_IMPORT',config_path=root/m['source_config'],dataset_path=root/m['dataset'],
                                   factory_version='1.7',kind='LEGACY_V1_7_GOLDEN_IMPORT')
            result['stats']=library.stats()
            atomic_json(root/'runs/reports/v18/library_import.json',result)
            return result
        finally: library.close()
    if args.command == 'production':
        factory=ProductionFactory(root,args.jobs_db,args.library_db)
        try:
            if args.action == 'status': result=factory.status()
            else:
                if not args.config: raise ValueError('Production configuration required')
                batch=factory.load_batch(args.config)
                if args.action == 'plan':
                    jobs=factory.plan(batch)
                    return {'requested':len(jobs),'counts':dict(Counter(j.status for j in jobs)),
                            'jobs':[{'job_id':j.job_id,'market':j.market,'timeframe':j.timeframe,'seed':j.seed,'evaluations':j.evaluations,'status':j.status,'error':j.error} for j in jobs]}
                result=factory.run(batch,resume=args.action=='resume')
            return {'total':result['total'],'counts':result['counts'],
                    'jobs':[{k:j[k] for k in ['job_id','market','timeframe','seed','status','attempts','generated','candidates','validation_pass','oos_pass','promoted','runtime','error']} for j in result['jobs']]}
        finally: factory.close()
    if args.command == 'factory':
        catalog=DataCatalog(root); library=StrategyLibrary(root/'library/strategies.sqlite'); production=ProductionFactory(root)
        try:
            golden=fast_regression(root)
            return {'factory':'SQX STRATEGY FACTORY','factory_version':VERSION,'grammar':'V1.7 FROZEN',
                    'golden_fast_regression':golden['status'],
                    'datasets':{'markets':len({r['market'] for r in catalog.records}), 'timeframes':len({r['timeframe'] for r in catalog.records}),
                                'available_combinations':sum(r['status']=='DATASET_AVAILABLE' for r in catalog.records)},
                    'library':library.stats(),'production':production.status()['counts']}
        finally: library.close(); production.close()
    raise ValueError('Unknown operation')
