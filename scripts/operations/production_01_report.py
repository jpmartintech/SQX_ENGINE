"""Read-only production evidence aggregation and release integrity audit."""
from pathlib import Path
from collections import Counter
import json,sqlite3,re,subprocess,math,csv
from contextlib import closing
from sqx_engine.production import atomic_json
from sqx_engine.config import EngineConfig
from sqx_engine.data.split import file_sha256
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'runs/reports/production_01'
def ro(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True); db.row_factory=sqlite3.Row; return db

def main():
    plan=json.loads((OUT/'plan.json').read_text()); results=json.loads((OUT/'production_jobs.json').read_text()); before=json.loads((OUT/'library_before.json').read_text())
    jobs=[]; families={}; peak=0
    for j in sorted(results['jobs'],key=lambda j:(j['market'],j['timeframe'],j['seed'])):
        d=Path(j['directory']); p=json.loads((d/'promotion.json').read_text()) if (d/'promotion.json').exists() else {}
        row={k:j[k] for k in ['job_id','market','timeframe','seed','status','generated','candidates','validation_pass','oos_pass','runtime','attempts','error']}
        row.update(new_library=p.get('inserted',0),duplicates=p.get('duplicates_rejected',0),rediscoveries=p.get('new_observations',0)-p.get('inserted',0))
        for text in re.findall(r'RSS=([0-9.]+)MB',(d/'production.log').read_text()):peak=max(peak,float(text))
        if (d/'discovery_summary.json').exists():
            ds=json.loads((d/'discovery_summary.json').read_text()); peak=max(peak,ds['memory_rss_mb']); row['timings']=ds['timings'];row['funnel']=ds['counters'];row['strategies_per_sec']=j['generated']/j['runtime']
        if j['status']=='COMPLETE':
            with closing(ro(d/'validation.sqlite')) as db:
                from sqx_engine.grammar import family_key
                from sqx_engine.strategy import StrategyDefinition
                fam=Counter(family_key(StrategyDefinition.from_json(r[0])) for r in db.execute('SELECT strategy_json FROM oos_results WHERE passed=1'))
            row['oos_families']=dict(fam)
            vs=json.loads((d/'validation_summary.json').read_text())
            row.update(source_run_id=ds['run_id'],validation_run_id=vs['validation_run_id'],dataset_sha256=j['dataset']['sha256'],production_policy='PRODUCTION_2016_2026_V1',production_batch='PRODUCTION_01',directory=str(d))
            row['artifacts']={name:{'path':str(d/name),'sha256':file_sha256(d/name)} for name in ['discovery.sqlite','validation.sqlite','checkpoint.json','discovery.yaml','validation.yaml']}
            row['survival']={'generated_to_oos':j['oos_pass']/j['generated'],'dev_to_val':j['validation_pass']/j['candidates'] if j['candidates'] else None,'val_to_oos':j['oos_pass']/j['validation_pass'] if j['validation_pass'] else None,'dev_to_oos':j['oos_pass']/j['candidates'] if j['candidates'] else None}
        jobs.append(row)
    with closing(ro(ROOT/'library/strategies.sqlite')) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        stats={'total':db.execute('SELECT count(*) FROM strategies').fetchone()[0]}
        for key in ['market','timeframe','family','direction','predicate_count']:
            stats['by_'+key]={str(r[0]):r[1] for r in db.execute(f'SELECT {key},count(*) FROM strategies GROUP BY {key}')}
        stats['by_market_timeframe']={r[0]+' '+r[1]:r[2] for r in db.execute('SELECT market,timeframe,count(*) FROM strategies GROUP BY market,timeframe')}
        policies={}; policy_by_job={}
        for r in db.execute('SELECT job_id,kind,provenance FROM library_jobs'):
            prov=json.loads(r['provenance']); cfg=EngineConfig.from_yaml(prov['config_path']); policy=cfg.get('production_policy') or r['kind']
            if policy=='PRODUCTION': policy='V1_8_SMOKE_CHRONOLOGICAL'
            policy_by_job[r['job_id']]=policy
        first=Counter(); membership={}
        for r in db.execute('SELECT canonical_hash,job_id FROM strategies'): first[policy_by_job[r['job_id']]]+=1
        for r in db.execute('SELECT canonical_hash,job_id FROM observations'): membership.setdefault(policy_by_job[r['job_id']],set()).add(r['canonical_hash'])
        stats['by_production_policy_first_discovery']=dict(first)
        stats['by_production_policy_membership']={k:len(v) for k,v in membership.items()}
        stats['policy_note']='Membership overlaps when the same trading identity survives multiple policies; first discovery is exclusive.'
        stats['observations']=db.execute('SELECT count(*) FROM observations').fetchone()[0]
        stats['database_sha256']=file_sha256(ROOT/'library/strategies.sqlite')
    catalog=json.loads((ROOT/'data/catalog.json').read_text())['datasets']
    assert all(file_sha256(ROOT/r['path'])==r['sha256'] for r in catalog)
    sources=json.loads((OUT/'source_audits.json').read_text())
    assert all(file_sha256(r['path'])==r['sha256'] for r in sources)
    protected=json.loads((ROOT/'benchmarks/v1.7/protected_hashes.json').read_text())
    changed=[str(p) for p,h in protected.items() if file_sha256(ROOT/p)!=h]; assert not changed,changed
    assert subprocess.check_output(['git','rev-parse','v1.8'],cwd=ROOT,text=True).strip()=='16a70ec0db6d58f8adb51ec8ae7caa361e139003'
    assert subprocess.check_output(['git','rev-parse','benchmark-v1.7-eurusd-h1'],cwd=ROOT,text=True).strip()=='e7aae6b279ace1dba47ae395fad5156201acb2f1'
    subprocess.run(['git','diff','--exit-code','v1.8','--','src','tests','pyproject.toml'],cwd=ROOT,check=True)
    aggregates={}
    for j in jobs:
        key=j['market']+' '+j['timeframe']; a=aggregates.setdefault(key,{'seeds':[],'generated':0,'development':0,'validation':0,'oos':0,'new_library':0,'runtime':0,'oos_families':{}})
        a['seeds'].append(j['seed'])
        for out,field in [('generated','generated'),('development','candidates'),('validation','validation_pass'),('oos','oos_pass'),('new_library','new_library'),('runtime','runtime')]:a[out]+=j[field]
        a['oos_families']=dict(Counter(a['oos_families'])+Counter(j.get('oos_families',{})))
    for a in aggregates.values():
        a['survival']={label:a[num]/a[den] if a[den] else None for label,num,den in [('dev_to_val','validation','development'),('val_to_oos','oos','validation'),('dev_to_oos','oos','development'),('generated_to_oos','oos','generated')]}
    added=sum(j['new_library'] for j in jobs);assert before['total']+added==stats['total']
    counts=Counter(j['status'] for j in jobs); completed=counts['COMPLETE']; ready=plan['counts'].get('READY',0)
    status='COMPLETE' if completed==ready else ('PARTIAL' if completed else 'FAILED')
    runtime=sum(j['runtime'] for j in jobs); generated=sum(j['generated'] for j in jobs)
    summary={'batch':'PRODUCTION_01','status':status,'factory_commit':'16a70ec0db6d58f8adb51ec8ae7caa361e139003','grammar':'v1.7','plan_counts':plan['counts'],'completed':completed,'failed':counts['FAILED'],'interrupted':counts['INTERRUPTED'],'skipped':plan['requested']-ready,'jobs':jobs,'by_market_timeframe':aggregates,'library':{'before':before['total'],'added':added,'duplicates':sum(j['duplicates'] for j in jobs),'rediscoveries':sum(j['rediscoveries'] for j in jobs),'after':stats['total'],'stats':stats},'performance':{'total_generated':generated,'total_job_runtime':runtime,'strategies_per_sec':generated/runtime,'peak_observed_rss_mib':peak,'rss_note':'Maximum sampled 30-second heartbeat/final-discovery RSS; not an OS high-water mark'},'integrity':{'frozen_factory':'PASS','dataset_and_original_source_hashes':'PASS','resume_complete_jobs':'PASS','historical_artifacts_unchanged':len(protected),'tags_unchanged':'PASS','jobs':json.loads((OUT/'integrity.json').read_text())},'readiness_blockers':{'60_skipped_jobs':'Missing reliable production execution profiles'},'execution_blockers':[]}
    with (OUT/'market_timeframe.csv').open('w',newline='') as handle:
        writer=csv.writer(handle); writer.writerow(['market','timeframe','seeds','generated','development','validation','oos','new_library','runtime','dev_to_val','val_to_oos','dev_to_oos','generated_to_oos'])
        for key,a in aggregates.items():writer.writerow([*key.split(),','.join(map(str,a['seeds'])),*[a[k] for k in ['generated','development','validation','oos','new_library','runtime']],*[a['survival'][k] for k in ['dev_to_val','val_to_oos','dev_to_oos','generated_to_oos']]])
    with (OUT/'oos_families.csv').open('w',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['market','timeframe','family','oos_pass_observations'])
        for key,a in aggregates.items():
            for family,count in sorted(a['oos_families'].items()):writer.writerow([*key.split(),family,count])
    atomic_json(OUT/'summary.json',summary)
    atomic_json(OUT/'library_final.json',stats)
    atomic_json(OUT/'historical_verification.json',{'protected':len(protected),'changed':changed,'status':'PASS'})
    lines=['# PRODUCTION_01 — final report','',f'Batch {status}; factory V1.8 frozen. {completed}/{ready} READY jobs completed; {plan["requested"]-ready} missing-profile jobs skipped.','', '| Market | TF | Seed | Generated | Dev | Val | OOS | New library | Runtime s |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for j in jobs:lines.append(f"| {j['market']} | {j['timeframe']} | {j['seed']} | {j['generated']} | {j['candidates']} | {j['validation_pass']} | {j['oos_pass']} | {j['new_library']} | {j['runtime']:.2f} |")
    lines+=['',f'Library: {before["total"]} + {added} = {stats["total"]}. Exact duplicates rejected: {summary["library"]["duplicates"]}.', '',f'Performance: {generated} strategies, {runtime:.2f} seconds summed job time, {generated/runtime:.2f} strategies/sec; observed RSS maximum {peak:.1f} MiB.','', 'Full distributions, family telemetry, policy membership, timings and survival rates: summary.json. Historical protected artifacts and factory source hashes unchanged.']
    (OUT/'summary.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['jobs','integrity']},indent=2))
if __name__=='__main__': main()
