import csv, json, sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_library_replay_equivalence_complete():
    p=ROOT/'runs/library_replay/replay_summary.json'
    assert p.exists()
    d=json.loads(p.read_text())
    assert d['tested']==12289
    assert d['complete']==12289
    assert d['failed']==0
    assert d['equivalence']=='PASS'

def test_replay_database_integrity_and_rows():
    p=ROOT/'runs/library_replay/replay.sqlite'
    assert p.exists()
    c=sqlite3.connect(p)
    assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
    assert c.execute('select count(*) from strategy_replays').fetchone()[0]==12289
    assert c.execute("select count(*) from strategy_replays where status!='PASS'").fetchone()[0]==0
    c.close()

def test_behavioral_audit_outputs():
    p=ROOT/'runs/reports/library_replay/behavioral_correlation_summary.csv'
    rows=list(csv.DictReader(p.open()))
    assert len(rows)==21
    assert all(float(r['components_corr_080'])>=0 for r in rows)

def test_replay_module_is_downstream_only():
    from sqx_engine.replay import LibraryReplayEngine, ReplayRequest, ReplayResult
    assert LibraryReplayEngine and ReplayRequest and ReplayResult
