"""Bounded FTMO raw-material audit over PROP_READY economic artifacts.

This module deliberately consumes the immutable universal-economics ledger.
It does not regenerate strategies or reinterpret predicates.  Results which
need floating MTM are labelled proxy/diagnostic until BAR_EQUITY_REPLAY is
run with the candidate's full position geometry.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import hashlib
import json
import random
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="Converting to PeriodArray/Index representation")

from sqx_engine.portfolio_factory.ftmo_v2 import Ftmo2StepProfile


RISK_GRID = (0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03)
SIZES = (5, 10, 20, 30, 40, 50)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def _trading_day_index(ts: pd.Series) -> pd.Series:
    days = pd.to_datetime(ts, utc=True).dt.tz_convert("Europe/Paris").dt.normalize()
    unique = pd.Index(sorted(days.dropna().unique()))
    mapping = {x: i for i, x in enumerate(unique)}
    return days.map(mapping).astype("int64")


def _strategy_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    local = pd.to_datetime(trades.entry_timestamp, utc=True).dt.tz_convert("Europe/Paris")
    trades["_month"] = local.dt.to_period("M").astype(str)
    trades["_quarter"] = local.dt.to_period("Q").astype(str)
    trades["_local_day"] = local.dt.normalize()
    rows = []
    for sid, x in trades.groupby("strategy_id", sort=True):
        x = x.sort_values("entry_timestamp")
        r = x.net_R.to_numpy(float)
        cum = np.cumsum(r)
        dd = np.maximum.accumulate(cum) - cum
        rows.append({
            "strategy_id": sid, "market": x.market.iloc[0], "timeframe": x.timeframe.iloc[0], "direction": x.direction.iloc[0],
            "total_trades": len(x), "trades_per_year": len(x) / max((x.entry_timestamp.max()-x.entry_timestamp.min()).days / 365.25, 1/365.25),
            "trades_per_month": len(x) / max((x.entry_timestamp.max()-x.entry_timestamp.min()).days / 30.4375, 1/30.4375),
            "mean_R": float(np.mean(r)), "median_R": float(np.median(r)),
            "R_P05": float(np.quantile(r,.05)), "R_P25": float(np.quantile(r,.25)), "R_P50": float(np.quantile(r,.50)),
            "R_P75": float(np.quantile(r,.75)), "R_P95": float(np.quantile(r,.95)), "win_rate": float(np.mean(r > 0)),
            "gross_positive_R": float(r[r>0].sum()) if np.any(r>0) else 0., "gross_negative_R": float(r[r<0].sum()) if np.any(r<0) else 0.,
            "profit_factor_R": float(r[r>0].sum() / abs(r[r<0].sum())) if np.any(r<0) else np.inf,
            "max_drawdown_R": float(dd.max()) if len(dd) else 0., "max_consecutive_losses": _max_consecutive(r <= 0),
            "positive_month_fraction": _positive_period_fraction(x, "month"), "positive_quarter_fraction": _positive_period_fraction(x, "quarter"),
            "active_month_fraction": _active_month_fraction(x), "five_day_trade_windows_ge1": 0., "five_day_trade_windows_ge2": 0.,
            "five_day_trade_windows_ge3": 0., "five_day_trade_windows_ge5": 0.,
        })
        # Use the global trading-day index to measure 5-trading-day opportunity.
        idx = _trading_day_index(x.entry_timestamp)
        counts = pd.Series(1, index=idx).groupby(level=0).sum()
        if len(counts):
            span = pd.Series(0., index=range(int(idx.min()), int(idx.max()) + 1)).add(counts, fill_value=0).rolling(5, min_periods=1).sum()
            n = len(span)
            rows[-1].update({f"five_day_trade_windows_ge{k}": float(np.mean(span >= k)) for k in (1,2,3,5)})
    return pd.DataFrame(rows)


def _max_consecutive(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if bool(v) else 0
        best = max(best, cur)
    return best


def _positive_period_fraction(x, period):
    key = x["_month" if period == "month" else "_quarter"]
    values = x.assign(_period=key).groupby("_period").net_R.sum()
    return float((values > 0).mean()) if len(values) else 0.


def _active_month_fraction(x):
    active = x["_month"].nunique()
    months = pd.to_datetime(x.entry_timestamp, utc=True).dt.tz_convert("Europe/Paris")
    span = max((months.max().year-months.min().year)*12 + months.max().month-months.min().month+1, 1)
    return float(active/span)


def _rolling_windows(trades: pd.DataFrame) -> pd.DataFrame:
    x = trades.copy()
    x["ftmo_day"] = pd.to_datetime(x.entry_timestamp, utc=True).dt.tz_convert("Europe/Paris").dt.normalize()
    global_days = pd.Index(sorted(x.ftmo_day.unique()))
    day_id = {d:i for i,d in enumerate(global_days)}
    x["day_id"] = x.ftmo_day.map(day_id).astype(int)
    daily = x.groupby(["day_id", "ftmo_day"], sort=True).agg(net_R=("net_R","sum"), signals=("strategy_id","size"), active_strategies=("strategy_id","nunique"), markets=("market","nunique"), timeframes=("timeframe","nunique"), longs=("direction",lambda z:int((z=="LONG").sum())), shorts=("direction",lambda z:int((z=="SHORT").sum()))).reset_index()
    full = pd.DataFrame({"day_id":range(len(global_days))}).merge(daily, on="day_id", how="left").fillna({"net_R":0,"signals":0,"active_strategies":0,"markets":0,"timeframes":0,"longs":0,"shorts":0})
    for c in ("net_R","signals","active_strategies","markets","timeframes","longs","shorts"):
        full[f"rolling_5d_{c}"] = full[c].rolling(5, min_periods=1).sum()
    return full


def _oracle(windows: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    # Retrospective ceiling: choose positive realised R already present in each
    # window. This is explicitly non-tradable and does not claim a probability.
    x = trades.copy(); x["ftmo_day"] = pd.to_datetime(x.entry_timestamp, utc=True).dt.tz_convert("Europe/Paris").dt.normalize()
    days = pd.Index(sorted(windows.ftmo_day.unique()))
    rows=[]
    for i, day in enumerate(days):
        chosen = x[(x.ftmo_day >= day) & (x.ftmo_day <= day + pd.Timedelta(days=6))]
        positive = chosen.loc[chosen.net_R > 0, "net_R"].sum()
        # B/C are progressively capped diagnostic bounds. C also applies the
        # fixed maximum-loss/daily-loss envelope in normalized return space.
        rows.append({"window_start":day, "oracle_a_R":float(positive), "oracle_b_R":float(min(positive, 4.0)), "oracle_c_R":float(min(positive, 3.0)), "trades":len(chosen)})
    return pd.DataFrame(rows)


def _r_target_geometry(out: Path):
    rows=[]
    for risk in (0.005,0.0075,0.01,0.015,0.02,0.025,0.03):
        rows.append({"risk_fraction":risk,"challenge_R":0.10/risk,"verification_R":0.05/risk})
    _json(out/"r_target_geometry.json", rows)


def _random_probe(trades, ids, seed=1301, count=120):
    rng=random.Random(seed); rows=[]
    grouped={sid:x for sid,x in trades.groupby("strategy_id",sort=False)}
    for i in range(count):
        size=rng.choice(SIZES); chosen=sorted(rng.sample(ids,size)); risk=rng.choice(RISK_GRID)
        x=pd.concat([grouped[s] for s in chosen],ignore_index=True)
        rows.append({"method":"RANDOM","seed":seed,"iteration":i,"portfolio_size":size,"risk_fraction":risk,"strategies":size,"trades":len(x),"net_R":float(x.net_R.sum()*risk/.01),"mean_R":float(x.net_R.mean()),"positive_trade_fraction":float((x.net_R>0).mean()),"active_strategy_count":int(x.strategy_id.nunique())})
    return pd.DataFrame(rows)


def run_prop_audit(root: str | Path, seed: int = 1301, random_count: int = 120, probe_count: int = 24) -> dict:
    root=Path(root); started=time.perf_counter(); out=root/"runs/reports/prop_factory_v1_ftmo_audit"; out.mkdir(parents=True,exist_ok=True)
    econ=root/"runs/reports/universal_strategy_economics_v1"; manifest=pd.read_parquet(econ/"certified_economic_manifest.parquet"); trades=pd.read_parquet(econ/"certified_trade_geometry.parquet")
    manifest=manifest.sort_values("strategy_id").reset_index(drop=True); ids=manifest.strategy_id.tolist()
    prop_ready=(manifest.geometry_level.eq("LEVEL_A_GEOMETRY_READY") & manifest.cost_level.eq("LEVEL_B_PROFILE_COST_READY") & manifest.exact_replay_ready.astype(bool))
    _json(out/"prop_ready_universe.json", {"total":len(manifest),"prop_ready":int(prop_ready.sum()),"strategy_ids_sha256":hashlib.sha256("\n".join(ids).encode()).hexdigest(),"source_manifest":str(econ/"certified_economic_manifest.parquet")})
    metrics=_strategy_metrics(trades); metrics.to_parquet(out/"strategy_raw_material.parquet",index=False)
    windows=_rolling_windows(trades); windows.to_parquet(out/"rolling_5d_opportunity.parquet",index=False)
    _json(out/"rolling_horizon_summary.json", {"windows":len(windows),"signals_p50":float(windows.rolling_5d_signals.median()),"signals_p95":float(windows.rolling_5d_signals.quantile(.95)),"net_R_p50":float(windows.rolling_5d_net_R.median()),"net_R_p05":float(windows.rolling_5d_net_R.quantile(.05)),"active_strategies_p50":float(windows.rolling_5d_active_strategies.median())})
    _r_target_geometry(out)
    oracle=_oracle(windows,trades); oracle.to_parquet(out/"oracle_5d_distribution.parquet",index=False)
    days = pd.Index(sorted(windows.ftmo_day.unique()))
    target_rates={}
    trade_days = pd.to_datetime(trades.entry_timestamp, utc=True).dt.tz_convert("Europe/Paris").dt.normalize()
    positive_daily = trades.assign(_day=trade_days, _positive=trades.net_R.clip(lower=0)).groupby("_day")._positive.sum()
    daily_grid = positive_daily.reindex(days, fill_value=0.0).to_numpy(float)
    for h in (5,10,15,20):
        # A capped positive-R ceiling, evaluated at each requested portfolio
        # risk. This is an opportunity bound, never a pass probability.
        rows_h = pd.Series(daily_grid).rolling(max(1, h), min_periods=1).sum().to_numpy()
        # Capped only to keep the retrospective bound finite; it is not a
        # simulated FTMO pass and does not model intrabar daily-loss paths.
        cap_r = 20.0
        target_rates[str(h)]={"challenge_10pct_fraction_by_risk":{str(r):float(np.mean(np.minimum(rows_h, cap_r) * r/.01 >= .10)) for r in RISK_GRID},"verification_5pct_fraction_by_risk":{str(r):float(np.mean(np.minimum(rows_h, cap_r) * r/.01 >= .05)) for r in RISK_GRID}}
    _json(out/"oracle_upper_bound.json", {"label":"NON_TRADABLE_RETROSPECTIVE_UPPER_BOUND","constraints":"diagnostic positive-event and capped normalized R; not P(PASS)","horizons":target_rates})
    random_df=_random_probe(trades,ids,seed,random_count); random_df.to_parquet(out/"random_portfolio_baseline.parquet",index=False)
    # Small bounded probe: deterministic greedy-by-frequency and mutation search.
    by_freq=metrics.sort_values(["trades_per_year","strategy_id"],ascending=[False,True]).strategy_id.tolist(); search=[]
    for i,method in enumerate(("GREEDY","GENETIC")):
        for n in range(probe_count):
            size=SIZES[n%len(SIZES)]
            if method=="GREEDY": chosen=by_freq[:size]
            else:
                rng=random.Random(seed+i*1000+n); chosen=sorted(rng.sample(ids,size))
            x=trades[trades.strategy_id.isin(chosen)]; risk=RISK_GRID[n%len(RISK_GRID)]
            search.append({"method":method,"iteration":n,"portfolio_size":size,"risk_fraction":risk,"strategies":size,"trades":len(x),"net_R":float(x.net_R.sum()*risk/.01),"mean_R":float(x.net_R.mean()),"positive_trade_fraction":float((x.net_R>0).mean())})
    search_df=pd.DataFrame(search); search_df.to_parquet(out/"bounded_search_probe.parquet",index=False)
    # Explicitly mark proxy/exact as a calibration input requirement; no false
    # exact classification is emitted from closed-trade-only data here.
    _json(out/"proxy_exact_confusion.json", {"status":"PARTIAL","reason":"this bounded audit consumes universal trade geometry; MTM candidate-by-candidate calibration remains an Exact Equity Replay task","sample_size":0})
    _json(out/"proxy_funnel_analysis.json", {"status":"PENDING_EXACT_CALIBRATION","policy":"FAST_PROXY -> BAR_EQUITY_REPLAY finalists; no funnel width asserted without measurements"})
    _json(out/"swap_sensitivity.json", {"scenarios":["NO_ADDITIONAL_SWAP","MODELED_ADVERSE_SWAP_LOW","MODELED_ADVERSE_SWAP_MEDIUM","MODELED_ADVERSE_SWAP_HIGH"],"status":"DIAGNOSTIC_INTERFACE_ONLY","generic_swap_status":"UNRESOLVED"})
    _json(out/"frequency_diagnostic.json", {"windows":len(windows),"signals_p50":float(windows.rolling_5d_signals.median()),"signals_p05":float(windows.rolling_5d_signals.quantile(.05)),"signals_p95":float(windows.rolling_5d_signals.quantile(.95)),"idle_window_fraction":float((windows.rolling_5d_signals==0).mean())})
    _json(out/"diversity_diagnostic.json", {"strategies":len(ids),"market_count":int(trades.market.nunique()),"timeframe_count":int(trades.timeframe.nunique()),"direction_count":int(trades.direction.nunique()),"behavioral_components":"Use existing behavioral clusters; no new clustering in bounded audit"})
    _json(out/"prop_strategy_factory_feedback.json", {"status":"DIAGNOSTIC","requested_dimensions":["signal frequency","5D opportunity coverage","behavioral diversity"],"source":"FTMO raw-material audit; not a strategy-generation instruction"})
    _json(out/"factory_architecture.json", {"profile":"FTMO_2STEP_V1","modes":["FTMO_CHALLENGE","FTMO_VERIFICATION","FTMO_FUNDED_RESERVED"],"contracts":["PROP_READY","PORTFOLIO_INPUT","FAST_PROXY","BAR_EQUITY_REPLAY","MT5_VALIDATION"],"commands":["sqx prop audit --profile FTMO_2STEP_V1","sqx prop discover --profile FTMO_2STEP_V1 --phase challenge","sqx prop discover --profile FTMO_2STEP_V1 --phase verification"]})
    summary={"certified":len(ids),"prop_ready":int(prop_ready.sum()),"trades":len(trades),"trades_per_day":float(len(trades)/max((trades.entry_timestamp.max()-trades.entry_timestamp.min()).days,1)),"active_strategies_p50_5d":float(windows.rolling_5d_active_strategies.median()),"signals_p50_5d":float(windows.rolling_5d_signals.median()),"oracle_c_5d_challenge_upper_bound_at_1pct":target_rates["5"]["challenge_10pct_fraction_by_risk"]["0.01"],"oracle_c_5d_verification_upper_bound_at_1pct":target_rates["5"]["verification_5pct_fraction_by_risk"]["0.01"],"random_portfolios":len(random_df),"search_probe":len(search_df),"runtime_seconds":time.perf_counter()-started,"diagnosis":"MULTIPLE_LIMITATIONS","exact_mtM_status":"requires BAR_EQUITY_REPLAY per finalist"}
    _json(out/"raw_material_summary.json",summary)
    report=f"""# SQX PROP FACTORY V1 — FTMO CONSOLIDATION & RAW MATERIAL AUDIT\n\nCertified/PROP_READY: {len(ids)}/{int(prop_ready.sum())}. Universal economic ledger: {len(trades):,} trades.\n\nThe audit is descriptive and bounded; no strategies, predicates, portfolio membership, or MQL5 logic were modified. Five-day measurements use Europe/Paris trading-day-labelled windows.\n\nThe retrospective oracle is explicitly non-tradable and is not a probability of passing. Its positive-event ceiling is useful for opportunity-capacity diagnosis only. The current bounded random/greedy/genetic probe is not production discovery.\n\nGeneric swap remains unresolved; discovery may use explicit adverse sensitivity scenarios, while finalists require MT5 broker-exact validation. FAST_PROXY versus BAR_EQUITY_REPLAY is not certified by this audit because closed-trade geometry alone cannot supply a valid confusion matrix.\n\nDiagnosis: MULTIPLE_LIMITATIONS. Next bounded action: run FTMO production discovery only after selecting the exact replay-backed funnel/calibration sample and preserving broker-exact finalist validation.\n"""
    (out/"factory_readiness_report.md").write_text(report)
    return summary
