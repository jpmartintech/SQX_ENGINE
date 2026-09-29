import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from crypto_clean_reboot_v1 import fast_bounded, bounded_replay

def _bars():
    ts=pd.date_range('2020-01-01', periods=5, freq='15min', tz='UTC')
    return {'BTC':pd.DataFrame({'timestamp':ts,'close':[100.,101.,99.,102.,101.]})}

def _events():
    ts=pd.date_range('2020-01-01', periods=5, freq='15min', tz='UTC')
    return [{'entry_time':ts[0].value,'exit_time':ts[1].value,'direction':'LONG','r':1.,'entry_price':100.,'exit_price':101.,'entry_index':0,'exit_index':1,'asset':'BTC'}]

def test_fast_bounded_matches_reference_numeric_kernel():
    a=bounded_replay([{**_events()[0], 'entry_time':pd.Timestamp(_events()[0]['entry_time']), 'exit_time':pd.Timestamp(_events()[0]['exit_time'])}], _bars())
    b=fast_bounded(_events(), _bars())
    assert a['trades']==b['trades']
    for k in ('return','pf','economic_expectancy','maxdd','minimum_equity'):
        if k == 'pf' and a[k] == float('inf') and b[k] >= 1e29:
            continue
        assert abs(a[k]-b[k]) < 1e-12

def test_fast_summary_has_no_negative_equity_on_sequential_losses():
    ts=pd.date_range('2020-01-01', periods=5, freq='15min', tz='UTC')
    e=[]
    for i in range(4):
        e.append({'entry_time':ts[i].value,'exit_time':ts[i+1].value,'direction':'LONG','r':-1.,'entry_price':100.,'exit_price':99.,'entry_index':i,'exit_index':i+1,'asset':'BTC'})
    z=fast_bounded(e,_bars())
    assert z['minimum_equity'] > 0
    assert not z['ruin']
