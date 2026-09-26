from pathlib import Path
import csv
FIELDS=("timestamp","portfolio_id","strategy_id","event","symbol","timeframe","direction","price","volume","stop","requested_risk","balance","equity","floating_pnl","open_risk","message")
def import_mt5_log(path):
    with Path(path).open(newline="") as f:return [{k:r.get(k,"") for k in FIELDS} for r in csv.DictReader(f)]
def compare_mt5_log(path,expected,tolerances=None):
    tol={"price":1e-5,"stop":1e-5,**(tolerances or {})};actual=import_mt5_log(path);diff=[]
    for i,(a,e) in enumerate(zip(actual,expected)):
        for k in ("timestamp","strategy_id","direction"):
            if str(a.get(k))!=str(e.get(k)):diff.append({"index":i,"field":k,"class":"LOGICAL_MISMATCH"})
        for k in ("price","stop"):
            try:
                if abs(float(a.get(k,0))-float(e.get(k,0)))>tol[k]:diff.append({"index":i,"field":k,"class":"EXECUTION_OR_LOGICAL_MISMATCH"})
            except (TypeError,ValueError):pass
    return {"status":"PASS" if not diff and len(actual)==len(expected) else "FAIL","actual_events":len(actual),"expected_events":len(expected),"differences":diff,"tolerances":tol}
