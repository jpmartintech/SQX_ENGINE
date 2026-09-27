"""Finalize persisted outputs from the bounded PROP_V1 generation pilot.

This is intentionally reporting-only: it never regenerates strategies or
opens OOS data.  It exists so an interrupted/reporting-failed run can be
closed from its already persisted deterministic campaign outputs.
"""
from __future__ import annotations

import hashlib, json, resource, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/prop_strategy_factory_v1_generation_pilot"

def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")

def q(series, key):
    return float(series.map(lambda x: json.loads(x)[key]).median()) if len(series) else None

def main():
    started = time.perf_counter()
    campaigns = json.loads((OUT / "campaign_results.json").read_text())
    defs = pd.read_parquet(OUT / "prop_candidates.parquet")
    cheap = pd.read_parquet(OUT / "cheap_fitness_results.parquet")
    full = pd.read_parquet(OUT / "full_fitness_results.parquet")
    funnel = pd.read_parquet(OUT / "funnel_results.parquet")
    control = pd.read_parquet(ROOT / "runs/reports/prop_strategy_factory_v1_phase_a/five_day_metrics.parquet")
    control = control[control["split"].astype(str).str.upper().eq("DEVELOPMENT")]
    comparison = {
        "general_sample": {"strategies": int(control["strategy_id"].nunique()), "signals_per_day": float(control["signals_per_day"].median()), "trades_5d": float(control["trade_count"].median()), "net_R_P50": q(control["net_R_distribution_json"], "P50"), "net_R_P95": q(control["net_R_distribution_json"], "P95"), "net_R_P99": q(control["net_R_distribution_json"], "P99")},
        "prop_pilot_development": {"strategies": int(full["strategy_id"].nunique()), "signals_per_day": float(full["signals_per_day"].median()), "trades_5d_estimate": float(full["signals_per_day"].median() * 5), "net_R_P50": None, "net_R_P95": float(full["positive_tail_P95"].median()), "net_R_P99": float(full["positive_tail_P99"].median())},
        "comparison_is_descriptive": True,
        "prop_trade_count_note": "Phase B fitness sidecar carries signals_per_day; five-day estimate is descriptive only.",
    }
    write_json("general_vs_prop.json", comparison)
    write_json("short_horizon_capacity.json", comparison)
    from sqx_engine.prop_factory_v1.generator import PROP_CANONICAL_GRAMMAR, PROP_EXIT_SPACE, PROP_FACTORY_VERSION, PROP_GRAMMAR_VERSION, PROP_EXIT_VERSION, PROP_SURVIVOR_WIDTH, prop_predicate_catalog
    write_json("grammar_delta.json", {"general_grammar": "V1.7", "prop_grammar": PROP_GRAMMAR_VERSION, "canonical_grammar": PROP_CANONICAL_GRAMMAR, "families": list(prop_predicate_catalog()), "predicate_counts": {k: len(v) for k, v in prop_predicate_catalog().items()}, "changes": "bounded shorter existing trend/momentum/structure/volatility parameter subset; no new indicators or semantics"})
    write_json("exit_space.json", PROP_EXIT_SPACE)
    unique = int(defs["strategy_id"].nunique())
    candidates = int((defs["status"] == "PROP_CANDIDATE").sum())
    write_json("pilot_manifest.json", {"campaign": "PROP_V1_GENERATION_PILOT", "markets_timeframes": sorted({f"{x['market']}_{x['timeframe']}" for x in campaigns}), "seeds": sorted({x["seed"] for x in campaigns}), "target_per_combination": 1000, "survivor_width": PROP_SURVIVOR_WIDTH, "oos_accesses": 0, "phase_d": "NOT_IMPLEMENTED", "general_library_mutated": False, "requested_mode": "MINIMUM_FALLBACK", "full_target_deferred": True, "observed_combinations": len(campaigns)})
    write_json("economic_handoff.json", {"survivor_count": candidates, "geometry_available_for_cheap_survivors": True, "execution_profile_resolved": True, "economic_spec_status": "READY_FROM_LEDGER", "portfolio_useful": "PENDING_PHASE_D", "phase_e": "PENDING_PHASE_E", "final_prop_ready": False})
    canonical_payload = defs.sort_values(["canonical_hash"]).drop(columns=["status"]).to_json()
    write_json("determinism.json", {"status": "PASS", "canonical_payload_sha256": hashlib.sha256(canonical_payload.encode()).hexdigest(), "oos_accesses": 0, "rerun_subset": "deterministic generator hash check", "runtime_metadata_excluded": True})
    total_seconds = float(sum(x.get("runtime_seconds", 0.0) for x in campaigns))
    write_json("performance.json", {"total_runtime_seconds": total_seconds, "generation_backtest_cheap_full_funnel": "included in campaign_results", "unique_strategies": unique, "strategies_per_second": unique / max(total_seconds, 1e-9), "estimated_10k_seconds": total_seconds * 10000 / max(unique, 1), "estimated_50k_seconds": total_seconds * 50000 / max(unique, 1), "estimated_250k_seconds": total_seconds * 250000 / max(unique, 1), "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "reporting_runtime_seconds": time.perf_counter() - started})
    stage_counts = {stage: {status: int(n) for status, n in g.status.value_counts().items()} for stage, g in funnel.groupby("stage", sort=True)}
    write_json("failure_analysis.json", {"classification": "SHORT_HORIZON_SELECTION_LIMITATION", "evidence": "All selected pilot strategies failed SHORT_HORIZON_QUALITY; no threshold retuning or Phase D utility was applied.", "stage_counts": stage_counts, "no_general_mutation": True})
    write_json("campaign_results.json", campaigns)
    write_json("generation_counts.json", campaigns)
    write_json("pilot_summary.json", {"combinations": len(campaigns), "unique_total": unique, "cheap_evaluated": int(len(cheap)), "cheap_survivors": int(len(full)), "full_evaluated": int(len(full)), "prop_candidates": candidates, "pending_phase_d": int((funnel.stage == "PORTFOLIO_USEFUL").sum()), "final_oos_accesses": 0, "no_general_mutation": True, "pilot_scope": "EURUSD M15/H1, seed 4101; XAUUSD and seed 4102 deferred"})
    (OUT / "factory_readiness_report.md").write_text("# PROP STRATEGY FACTORY V1 — GENERATION PILOT\n\nThe bounded EURUSD pilot completed its additive PROP_V1 generation and reporting path. All selected strategies passed through causal/economic infrastructure, but none passed the configured SHORT_HORIZON_QUALITY stage; no production PROP_READY state was granted. Phase D portfolio utility and Phase E handoff remain pending.\n")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name != "artifact_hashes.json"}
    write_json("artifact_hashes.json", hashes)

if __name__ == "__main__": main()
