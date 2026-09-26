"""Compare a real MT5 Round 2E trace with the frozen MT5-feed expectation."""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd

CLASS_NAMES={"predicate":"PREDICATE_BOOLEAN","raw":"RAW_SIGNAL","admission":"ENTRY_ADMISSION"}

def compare(expected: Path, observed: Path, output: Path, expected_raw: Path | None = None, observed_raw: Path | None = None):
    e=pd.read_csv(expected); o=pd.read_csv(observed)
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for _,x in e.iterrows():
        key=(x.strategy_id,x.signal_bar_time,x.predicate_1_id)
        z=o[(o.strategy_id==key[0])&(o.signal_bar_time==key[1])]
        if len(z):
            y=z.iloc[0]
            for n in range(1,5):
                if x[f'predicate_{n}_id']:
                    rows.append({'strategy_id':x.strategy_id,'signal_bar_time':x.signal_bar_time,'predicate_id':x[f'predicate_{n}_id'],'expected_value':x[f'predicate_{n}_numeric_value'],'observed_value':y.get(f'predicate_{n}_numeric_value','UNRESOLVED'),'expected_result':x[f'predicate_{n}_result'],'observed_result':y.get(f'predicate_{n}_result','UNRESOLVED'),'classification':'EXACT_MATCH' if str(x[f'predicate_{n}_result'])==str(y.get(f'predicate_{n}_result','UNRESOLVED')) else 'PREDICATE_BOOLEAN'})
        else:
            rows.append({'strategy_id':x.strategy_id,'signal_bar_time':x.signal_bar_time,'predicate_id':'UNRESOLVED','expected_value':'','observed_value':'','expected_result':x.raw_signal,'observed_result':'UNRESOLVED','classification':'UNRESOLVED'})
    pd.DataFrame(rows).to_csv(output/'predicate_comparison_mt5_feed.csv',index=False)
    if expected_raw is not None and observed_raw is not None and observed_raw.exists():
        er=pd.read_csv(expected_raw); oraw=pd.read_csv(observed_raw)
        key=lambda x:(x.strategy_id,x.signal_bar_time,x.direction)
        ea={key(x):x for _,x in er.iterrows()}; oa={key(x):x for _,x in oraw.iterrows()}
        raw=[]
        for k in sorted(set(ea)|set(oa)):
            raw.append({'strategy_id':k[0],'signal_bar_time':k[1],'direction':k[2],'expected_raw_signal':k in ea,'observed_raw_signal':k in oa,'classification':'EXACT_MATCH' if (k in ea)==(k in oa) else 'RAW_SIGNAL'})
        pd.DataFrame(raw).to_csv(output/'raw_signal_comparison_mt5_feed.csv',index=False)
        # Admission fields are available on the complete predicate trace; this
        # file deliberately compares only the same-signal rows and leaves the
        # Python portfolio state explicit rather than inventing it.
        admission=[]
        for _,x in er.iterrows():
            z=o[(o.strategy_id==x.strategy_id)&(o.signal_bar_time==x.signal_bar_time)]
            if len(z):
                y=z.iloc[0]; admission.append({'strategy_id':x.strategy_id,'signal_bar_time':x.signal_bar_time,'python_raw_signal':bool(x.raw_signal),'mql5_raw_signal':bool(y.raw_signal),'mql5_position_gate':y.get('position_gate','UNRESOLVED'),'mql5_risk_gate':y.get('risk_gate','UNRESOLVED'),'mql5_entry_admitted':y.get('entry_admitted','UNRESOLVED'),'classification':'SAME_INPUT_TRACE_AVAILABLE'})
        pd.DataFrame(admission).to_csv(output/'portfolio_admission_comparison_mt5_feed.csv',index=False)
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--expected',default='runs/reports/deployment_engine_v1/portfolio_equivalence_round2/predicate_equivalence/python_expected_predicate_trace_mt5_feed.csv'); ap.add_argument('--expected-raw',default='runs/reports/deployment_engine_v1/portfolio_equivalence_round2/predicate_equivalence/python_expected_raw_signals_mt5_feed.csv'); ap.add_argument('--observed',required=True); ap.add_argument('--observed-raw'); ap.add_argument('--output',default='runs/reports/deployment_engine_v1/portfolio_equivalence_round2/predicate_equivalence'); a=ap.parse_args(); compare(Path(a.expected),Path(a.observed),Path(a.output),Path(a.expected_raw),Path(a.observed_raw) if a.observed_raw else None)
if __name__=='__main__': main()
