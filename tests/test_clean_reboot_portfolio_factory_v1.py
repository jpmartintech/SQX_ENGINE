import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/reports/crypto_clean_reboot_v1/portfolio_factory_v1'

def test_library_deduplication_and_firewall():
    d=json.loads((OUT/'DEDUPLICATION_REPORT.json').read_text())
    assert d['input_records']==7634
    assert d['unique_hashes']==7350
    assert d['hash_unique'] is True
    assert d['protected_lockbox_access']==0

def test_exact_portfolio_equivalence():
    d=json.loads((OUT/'portfolio_engine_equivalence.json').read_text())
    assert d['portfolios']==500
    assert d['pass']==500
    assert d['fail']==0
    assert d['maximum_metric_delta'] <= d['tolerance']

def test_search_budgets_and_pre_oos_freeze():
    r=json.loads((OUT/'random_portfolio_summary.json').read_text())
    g=json.loads((OUT/'genetic_summary.json').read_text())
    f=json.loads((OUT/'PRE_OOS_PORTFOLIO_FREEZE.json').read_text())
    assert r['unique'] >= 50000
    assert g['unique'] >= 100000
    assert f['status']=='FROZEN'
    assert f['oos_accessed'] is False
    assert f['lockbox_access']==0

def test_frontier_has_shared_equity_metrics():
    d=pd.read_parquet(OUT/'portfolio_frontier.parquet')
    assert len(d)>0
    assert {'dev_return','val_return','dev_maxdd','val_maxdd','dev_pf','val_pf'}.issubset(d.columns)
