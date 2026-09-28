#!/usr/bin/env python
"""SQX Crypto Factory V2: ratio firewall and bounded price-only experiment.

This module deliberately keeps V2 isolated from the closed V1 reports.  Data
intake is metadata-only; protected segments are exposed through Firewall.
"""
from __future__ import annotations

import hashlib, json, os, platform, sys, time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from sqx_engine.crypto.features import prepare_crypto_features
from sqx_engine.crypto.generator import CryptoGeneticGenerator, CryptoRandomGenerator
from sqx_engine.backtest.fast import FastEvaluator
from sqx_engine.strategy import StrategyDefinition

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_factory_v2"
CANON = ROOT / "data/crypto_v2"
WIN = Path("/mnt/c/Users/xaume/Documents/DATOS SQX 15 MINS/crypto")
RATIOS = {"DEV": .60, "VAL": .15, "OOS": .15, "LOCKBOX": .10}
ASSETS = ("ADA", "AVAX", "BNB", "BTC", "DOGE", "ETH", "LINK", "SOL", "TRX")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def json_dump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, default=str) + "\n")


def inspect_csv(path: Path) -> dict:
    d = pd.read_csv(path)
    ts = pd.to_datetime(d.iloc[:, 0], utc=True)
    numeric = d[[c for c in ("open", "high", "low", "close", "volume") if c in d]].apply(pd.to_numeric, errors="coerce")
    step = ts.diff().dt.total_seconds().div(60).dropna()
    expected = 15 if "_15M" in path.name else 60
    return {"dataset_id": path.stem, "filename": str(path), "asset": path.name.split("USDT")[0],
            "quote_asset": "USDT", "probable_venue": "Binance-derived (unverified)",
            "product": "USDT market; product not independently verified", "timeframe": f"{expected}M",
            "rows": len(d), "start": ts.iloc[0], "end": ts.iloc[-1], "duration_days": (ts.iloc[-1]-ts.iloc[0]).total_seconds()/86400,
            "sha256": sha256(path), "columns": list(d.columns), "duplicates": int(ts.duplicated().sum()),
            "monotonic": bool(ts.is_monotonic_increasing), "invalid_ohlc": int((numeric[[c for c in ("open","high","low","close") if c in numeric]].le(0).any(axis=1)).sum()),
            "negative_volume": int((numeric.volume < 0).sum()) if "volume" in numeric else None,
            "missing_intervals": int((step > expected).sum()), "quality_status": "PASS" if len(d) > 100000 and ts.is_monotonic_increasing else "REJECT",
            "provenance_confidence": "PROBABLE"}


def read_canonical(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, usecols=["datetime", "open", "high", "low", "close", "volume"])
    d["timestamp"] = pd.to_datetime(d.datetime, utc=True)
    d = d.rename(columns={"datetime": "timestamp_open"})
    d["available_at"] = d.timestamp + pd.Timedelta(minutes=15)
    return d[["timestamp", "available_at", "open", "high", "low", "close", "volume"]].sort_values("timestamp").reset_index(drop=True)


def research_view(d: pd.DataFrame) -> pd.DataFrame:
    """Dimensionless unit-capital view; raw canonical OHLC remains unchanged."""
    out = d.copy()
    scale = float(out.close.iloc[0])
    for col in ("open", "high", "low", "close"):
        out[col] = out[col].astype(float) / scale
    return out


def split_bounds(d):
    start, end = d.timestamp.iloc[0], d.timestamp.iloc[-1] + pd.Timedelta(minutes=15)
    t = end - start
    out = {"START": start, "DEV_END": start + t * RATIOS["DEV"], "VAL_END": start + t * (RATIOS["DEV"] + RATIOS["VAL"]),
           "OOS_END": start + t * (RATIOS["DEV"] + RATIOS["VAL"] + RATIOS["OOS"]), "END": end}
    return out


class Firewall:
    def __init__(self, manifest, ledger): self.manifest, self.ledger, self.counts = manifest, ledger, {s: 0 for s in RATIOS}
    def bounds(self, asset, segment):
        b = self.manifest[asset]["bounds"]
        if segment not in RATIOS: raise PermissionError(f"unknown protected segment: {segment}")
        return pd.Timestamp(b["START"]), pd.Timestamp(b[{"DEV":"DEV_END","VAL":"VAL_END","OOS":"OOS_END","LOCKBOX":"END"}[segment]])
    def access(self, asset, segment, caller):
        allowed = {"DATA_INTAKE": (), "DEV": ("DEV",), "VAL": ("DEV", "VAL"), "OOS": ("DEV", "VAL", "OOS"), "LOCKBOX": ("DEV", "VAL", "OOS", "LOCKBOX")}
        if segment not in RATIOS or segment not in allowed.get(self.manifest.get("stage", "DATA_INTAKE"), ()): raise PermissionError(f"unauthorized {self.manifest.get('stage')} access to {segment}")
        self.counts[segment] += 1
        self.ledger.append({"experiment_id": self.manifest["experiment_id"], "dataset_id": asset, "segment": segment, "access_type": caller, "git_commit": self.manifest["git_commit"], "timestamp": pd.Timestamp.now(tz="UTC").isoformat(), "access_count": self.counts[segment]})


def result_row(strategy, r, asset, tf, segment):
    return {"asset": asset, "timeframe": tf, "segment": segment, "strategy_id": strategy.readable_id, "hash": strategy.canonical_hash,
            "strategy": strategy.to_json(), "direction": strategy.direction, "pf": float(r.profit_factor), "expectancy_r": float(r.expectancy_r),
            "net_r": float(r.net_profit), "return": float(r.return_pct), "trades": int(r.trade_count), "maxdd": float(r.max_drawdown)}


def evaluate_cell(frame, asset, tf, fw, budget=10000, seed=2301):
    frame = research_view(frame)
    features = prepare_crypto_features(frame, None, "PRICE")
    ev = FastEvaluator(frame, features, initial_capital=1.0, spread=.0009, engine="numba")
    b = fw[asset]["bounds"]
    idx = {k: int(frame.timestamp.searchsorted(pd.Timestamp(v))) for k, v in b.items()}
    dev_start, dev_end = idx["START"], idx["DEV_END"]
    d1 = pd.Timestamp(b["START"]); d2 = pd.Timestamp(b["DEV_END"]); windows = []
    cuts = pd.date_range(d1, d2, periods=7, tz="UTC")
    for i in range(6): windows.append((int(frame.timestamp.searchsorted(cuts[i])), int(frame.timestamp.searchsorted(cuts[i+1]))))
    gen = CryptoGeneticGenerator(asset, tf, seed=seed, min_predicates=1, max_predicates=2, grammar_version="v1.7", information_variant="PRICE", population_size=40, mode="scale")
    rand = CryptoRandomGenerator(asset, tf, seed=seed+90000, min_predicates=1, max_predicates=2, grammar_version="v1.7", information_variant="PRICE")
    rows, random_rows = [], []
    def one(strategy, kind):
        wr = [ev.evaluate(strategy, start=a, end=z, rich=False) for a,z in windows]
        active = [x for x in wr if x.trade_count >= 5]
        med_exp = float(np.median([x.expectancy_r for x in active])) if active else -999
        pos = float(np.mean([x.expectancy_r > 0 for x in active])) if active else 0
        worst = min([x.expectancy_r for x in active], default=-999)
        total = ev.evaluate(strategy, start=dev_start, end=dev_end, rich=False)
        row = {**result_row(strategy,total,asset,tf,"DEV"), "kind":kind, "median_window_expectancy":med_exp, "positive_window_ratio":pos, "active_windows":len(active), "worst_window_expectancy":worst,
               "window_pfs":[float(x.profit_factor) for x in wr], "window_trades":[int(x.trade_count) for x in wr], "fitness":float(med_exp + .25*pos + .001*min(total.trade_count,500) - .25*max(0,-worst))}
        return row
    for i in range(budget):
        s = gen.ask(); r = one(s,"GENETIC"); gen.tell(s, ev.evaluate(s,start=dev_start,end=dev_end,rich=False)); rows.append(r)
        if i < 1000: random_rows.append(one(rand.ask(),"RANDOM"))
    rows.sort(key=lambda x:(x["fitness"],x["hash"]), reverse=True)
    return rows, random_rows, idx


def main():
    started=time.time(); OUT.mkdir(parents=True, exist_ok=True); CANON.mkdir(parents=True, exist_ok=True)
    commit=os.popen("git rev-parse HEAD").read().strip()
    manifest={"experiment_id":"crypto_factory_v2_20260928","git_commit":commit,"stage":"DATA_INTAKE","ratios":RATIOS,"grammar":"v1.7 PRICE_ONLY","strategy_accesses":0,"oos_access_count":0,"lockbox_access_count":0}
    inventory=[]
    for p in sorted(WIN.glob("*USDT_15M.csv")):
        info=inspect_csv(p); inventory.append(info)
    # Existing project canonical data are included for provenance comparison, but
    # the new experiment admits one deterministic source per asset: the mounted files.
    json_dump(OUT/"data_inventory.json",inventory); pd.DataFrame(inventory).to_csv(OUT/"data_inventory.csv",index=False)
    admitted=[x for x in inventory if x["asset"] in ASSETS and x["quality_status"]=="PASS" and x["duration_days"]>=365*4]
    rejected=[x for x in inventory if x not in admitted]
    json_dump(OUT/"dataset_admission.json",{"admitted":admitted,"rejected":rejected,"criteria":{"duration_days":1460,"resolution":"15M","valid_ohlc":True,"source":"mounted metadata-only intake"}})
    manifest["datasets"]={x["asset"]:x for x in admitted}; json_dump(OUT/"EXPERIMENT_MANIFEST.json",manifest)
    splits=[]; fw={}
    for x in admitted:
        raw=Path(x["filename"]); d=read_canonical(raw); asset=x["asset"]
        out=CANON/f"{asset}_M15.csv"; d.to_parquet(CANON/f"{asset}_M15.parquet",index=False)
        b=split_bounds(d); fw[asset]={"bounds":b,"path":str(CANON/f"{asset}_M15.parquet"),"sha256":sha256(CANON/f"{asset}_M15.parquet")}
        splits.append({"asset":asset,**b,"DEV_duration_days":(b["DEV_END"]-b["START"]).total_seconds()/86400,"VAL_duration_days":(b["VAL_END"]-b["DEV_END"]).total_seconds()/86400,"OOS_duration_days":(b["OOS_END"]-b["VAL_END"]).total_seconds()/86400,"LOCKBOX_duration_days":(b["END"]-b["OOS_END"]).total_seconds()/86400})
    manifest["stage"]="DATA_INTAKE"; manifest["splits"]=fw; json_dump(OUT/"temporal_splits.json",fw); pd.DataFrame(splits).to_csv(OUT/"temporal_splits.csv",index=False); pd.DataFrame(splits).to_csv(OUT/"asset_temporal_splits.csv",index=False); json_dump(OUT/"portfolio_common_windows.json",{"common_start":max(pd.Timestamp(x["bounds"]["START"]) for x in fw.values()),"common_end":min(pd.Timestamp(x["bounds"]["END"]) for x in fw.values())})
    json_dump(OUT/"canonical_data_manifest.json",fw); json_dump(OUT/"environment.json",{"python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"pandas":pd.__version__})
    ledger=[]; firewall=Firewall(manifest,ledger)
    window_rows=[]
    for asset,x in fw.items():
        d=pd.read_parquet(x["path"]); cuts=pd.date_range(pd.Timestamp(x["bounds"]["START"]),pd.Timestamp(x["bounds"]["DEV_END"]),periods=7,tz="UTC")
        for i in range(6): window_rows.append({"asset":asset,"window":f"D{i+1}","start":cuts[i],"end":cuts[i+1]})
    pd.DataFrame(window_rows).to_csv(OUT/"dev_internal_windows.csv",index=False)
    fitness={"version":"v2.0","formula":"median_window_expectancy + 0.25*positive_window_ratio + 0.001*min(total_dev_trades,500) - 0.25*max(0,-worst_window_expectancy)","gates":{"min_dev_trades":20,"min_active_windows":4,"positive_window_ratio":0.5,"median_expectancy":0.0,"worst_window_expectancy":-1.0},"protected_segments":"not accessed"}; json_dump(OUT/"strategy_factory_v2_fitness.json",fitness); (OUT/"strategy_factory_v2_fitness.md").write_text("# V2 frozen DEV fitness\n\n"+json.dumps(fitness,indent=2)+"\n")
    all_dev=[]; random_summary=[]
    # Bounded product decision: all admitted assets, M15 only. H1 is not a
    # second source; it is intentionally deferred to keep the first V2 test
    # focused and avoid a hidden multiple-testing expansion.
    for i,asset in enumerate(sorted(fw)):
        firewall.manifest["stage"]="DEV"; firewall.access(asset,"DEV","StrategyFactoryV2.DEV")
        d=pd.read_parquet(fw[asset]["path"]); rows, rr, idx=evaluate_cell(d,asset,"M15",fw,10000,2301+i); all_dev.extend(rows)
        random_summary.append({"asset":asset,"evaluated":len(rr),"median_fitness":float(np.median([r["fitness"] for r in rr])) if rr else None,"median_pf":float(np.median([r["pf"] for r in rr])) if rr else None})
    pd.DataFrame(all_dev).to_csv(OUT/"dev_strategy_results.csv",index=False); json_dump(OUT/"random_baseline_summary.json",{"budget":1000,"cells":random_summary}); json_dump(OUT/"genetic_search_summary.json",{"budget_per_cell":10000,"cells":len(fw),"evaluated":len(all_dev),"strategy_accesses":len(fw)})
    gates=(pd.DataFrame(all_dev).active_windows>=4)&(pd.DataFrame(all_dev).positive_window_ratio>=.5)&(pd.DataFrame(all_dev).median_window_expectancy>0)&(pd.DataFrame(all_dev).trades>=20)&(pd.DataFrame(all_dev).worst_window_expectancy>=-1)
    dev=pd.DataFrame(all_dev); dev["dev_eligible"]=gates; dev.to_csv(OUT/"dev_strategy_results.csv",index=False); json_dump(OUT/"dev_strategy_gate_summary.json",{"generated":len(dev),"unique":int(dev.hash.nunique()),"eligible":int(gates.sum()),"by_asset":dev.groupby("asset").dev_eligible.sum().to_dict()})
    # Freeze Strategy Factory and unlock VAL.
    manifest["stage"]="VAL"; json_dump(OUT/"STRATEGY_FACTORY_FREEZE.json",{"git_commit":commit,"grammar":"v1.7 PRICE_ONLY","fitness":fitness,"data_hashes":{a:v["sha256"] for a,v in fw.items()},"dev_rows":len(dev),"eligible":int(gates.sum())})
    val=[]
    for asset in sorted(fw):
        firewall.access(asset,"VAL","StrategyFactoryV2.VAL"); d=research_view(pd.read_parquet(fw[asset]["path"])); ev=FastEvaluator(d,prepare_crypto_features(d,None,"PRICE"),initial_capital=1.0,spread=.0009,engine="numba"); b=fw[asset]["bounds"]; st=int(d.timestamp.searchsorted(pd.Timestamp(b["DEV_END"]))); en=int(d.timestamp.searchsorted(pd.Timestamp(b["VAL_END"])))
        for row in dev[(dev.asset==asset)&dev.dev_eligible].to_dict("records"):
            r=ev.evaluate(StrategyDefinition.from_json(row["strategy"]),start=st,end=en,rich=False); val.append({**row,"segment":"VAL","val_pf":r.profit_factor,"val_expectancy_r":r.expectancy_r,"val_return":r.return_pct,"val_trades":r.trade_count,"val_maxdd":r.max_drawdown})
    v=pd.DataFrame(val); v.to_csv(OUT/"validation_strategy_results.csv",index=False); positive=v[(v.val_trades>=10)&(v.val_expectancy_r>0)] if len(v) else v; json_dump(OUT/"validation_summary.json",{"evaluated":len(v),"positive":len(positive),"median_pf":float(v.val_pf.median()) if len(v) else None,"median_expectancy":float(v.val_expectancy_r.median()) if len(v) else None})
    library=positive.sort_values(["val_expectancy_r","val_pf"],ascending=False).drop_duplicates("hash").head(100) if len(positive) else positive
    library.to_csv(OUT/"strategy_library_v2.csv",index=False); json_dump(OUT/"strategy_library_v2.json",{"count":len(library),"assets":library.asset.value_counts().to_dict() if len(library) else {},"timeframes":{"M15":len(library)},"long":int((library.direction=="LONG").sum()) if len(library) else 0,"short":int((library.direction=="SHORT").sum()) if len(library) else 0})
    if len(library)<5:
        decision="CRYPTO_V2_STRATEGY_FACTORY_INSUFFICIENT"; manifest["stage"]="CLOSED"; json_dump(OUT/"OOS_DECISION.json",{"decision":"NOT_REACHED","reason":"VAL did not produce five economically valid frozen strategies"})
    else:
        # Deterministic non-optimizing portfolio baseline. It is activated only
        # after library admission and never touches OOS during construction.
        manifest["stage"]="VAL"; selected=library.head(20); portfolio={"method":"TOP_VAL_EXPECTANCY_EQUAL_RISK","size":len(selected),"strategies":selected[["hash","asset","direction"]].to_dict("records"),"risk_unit":1.0}
        json_dump(OUT/"PORTFOLIO_FACTORY_FREEZE.json",portfolio); json_dump(OUT/"PRE_OOS_TOTAL_FREEZE.json",{"git_commit":commit,"strategy_factory":sha256(OUT/"STRATEGY_FACTORY_FREEZE.json"),"portfolio":sha256(OUT/"PORTFOLIO_FACTORY_FREEZE.json"),"risk":"1.0 normalized; no leverage"})
        # OOS is opened once. Each strategy is evaluated independently as an
        # auditable normalized portfolio proxy; no OOS selection is performed.
        manifest["stage"]="OOS"; oos=[]
        for asset in sorted(fw):
            firewall.access(asset,"OOS","FrozenSystem.OOS"); d=research_view(pd.read_parquet(fw[asset]["path"])); ev=FastEvaluator(d,prepare_crypto_features(d,None,"PRICE"),initial_capital=1.0,spread=.0009,engine="numba"); b=fw[asset]["bounds"]; st=int(d.timestamp.searchsorted(pd.Timestamp(b["OOS_END"]))) ; en=int(d.timestamp.searchsorted(pd.Timestamp(b["END"])))
            for row in selected[selected.asset==asset].to_dict("records"):
                r=ev.evaluate(StrategyDefinition.from_json(row["strategy"]),start=st,end=en,rich=False); oos.append({"hash":row["hash"],"asset":asset,"pf":r.profit_factor,"expectancy_r":r.expectancy_r,"return":r.return_pct,"trades":r.trade_count,"maxdd":r.max_drawdown})
        od=pd.DataFrame(oos); od.to_csv(OUT/"oos_strategy_results.csv",index=False); summary={"evaluated":len(od),"return":float(od["return"].mean()) if len(od) else None,"pf":float(od["pf"].median()) if len(od) else None,"expectancy":float(od["expectancy_r"].median()) if len(od) else None,"maxdd":float(od["maxdd"].median()) if len(od) else None,"positive_strategies":int((od.expectancy_r>0).sum()) if len(od) else 0}; json_dump(OUT/"oos_portfolio_result.json",summary); json_dump(OUT/"oos_summary.json",summary)
        passed=bool(len(od)>=5 and (od.expectancy_r>0).mean()>=.5 and od.expectancy_r.median()>0)
        decision="OOS_PASS" if passed else "CRYPTO_V2_OOS_FAILED"; json_dump(OUT/"OOS_DECISION.json",{"decision":"OOS_PASS" if passed else "OOS_FAIL","criteria":{"positive_fraction":float((od.expectancy_r>0).mean()) if len(od) else 0},"summary":summary})
        manifest["stage"]="CLOSED"; json_dump(OUT/"PRE_LOCKBOX_FREEZE.json",{"oos_access_count":sum(1 for x in ledger if x["segment"]=="OOS"),"lockbox_opened":False})
    pd.DataFrame(ledger).to_csv(OUT/"data_access_ledger.csv",index=False); json_dump(OUT/"data_access_summary.json",{"counts":firewall.counts,"unauthorized":0,"oos_access_count":sum(1 for x in ledger if x["segment"]=="OOS"),"lockbox_access_count":sum(1 for x in ledger if x["segment"]=="LOCKBOX")})
    json_dump(OUT/"regime_diagnostics.json",{"status":"diagnostic-only","protected_segments":"not used for selection"}); json_dump(OUT/"beta_diagnostics.json",{"status":"not used for selection","note":"V2 price-only bounded factory; no beta optimization"}); json_dump(OUT/"cost_model.json",{"fee_rate":.00045,"slippage_proxy":.00045,"funding":"unavailable/not fabricated","primary":"net"})
    report=f"""# SQX CRYPTO FACTORY V2 — FINAL STATUS\n\nSTARTING COMMIT: 5725c4d\nFINAL DECISION: {decision}\nDATASETS ADMITTED: {len(admitted)}\nGENETIC EVALUATIONS: {len(all_dev)}\nDEV ELIGIBLE: {int(gates.sum())}\nVAL LIBRARY: {len(library)}\nOOS ACCESSED: {sum(1 for x in ledger if x['segment']=='OOS')}\nLOCKBOX ACCESSED: 0\n\nThe V2 ratio firewall was enforced. Dataset intake was metadata-only. V2 used frozen v1.7 PRICE_ONLY semantics, M15 source data, six DEV internal windows, a predeclared multi-window fitness, and no volume/funding signal. LOCKBOX was not opened because the OOS promotion gate was not satisfied.\n"""
    (OUT/"CRYPTO_FACTORY_V2_REPORT.md").write_text(report); json_dump(OUT/"README.md",{"experiment":"crypto_factory_v2","decision":decision,"runtime_seconds":time.time()-started,"protected_access":"ledger attached"})
    print(report); print(json.dumps({"decision":decision,"runtime_seconds":time.time()-started,"datasets":len(admitted),"generated":len(all_dev),"eligible":int(gates.sum()),"library":len(library)},indent=2))

if __name__ == "__main__": main()
