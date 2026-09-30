import json
from pathlib import Path
import pandas as pd

OUT=Path('runs/reports/crypto_multicoin_portfolio_v1')

def test_multicoin_input_and_search_counts():
    d=json.loads((OUT/'INPUT_REPRODUCTION.json').read_text())
    assert d['total_instances']==92109
    assert json.loads((OUT/'RANDOM_SUMMARY.json').read_text())['unique']>=50000
    assert json.loads((OUT/'GENETIC_SUMMARY.json').read_text())['unique']>=100000

def test_multicoin_freeze_and_firewall():
    f=json.loads((OUT/'PRE_OOS_MULTICOIN_PORTFOLIO_FREEZE.json').read_text())
    a=json.loads((OUT/'DATA_ACCESS_LEDGER.json').read_text())
    assert f['status']=='FROZEN' and f['oos_accessed'] is True
    assert a['OOS_before_freeze']==0 and a['LOCKBOX']==0

def test_multicoin_frontier_has_shared_metrics():
    d=pd.read_parquet(OUT/'DEV_VAL_FRONTIER.parquet')
    assert len(d)>0
    assert {'dev_return','val_return','dev_maxdd','val_maxdd','asset_count'}.issubset(d.columns)
