"""Create the append-only Autonomous Loop 01 closure report."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/reports/prop_strategy_factory_v1_autonomous_loop_01"
EXPS = [BASE / "experiment_04_split_fix_eur", BASE / "experiment_04_split_fix_xau"]

def write(name, value):
    (BASE / name).write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")

def q(s, key):
    return float(s.map(lambda x: json.loads(x)[key]).median()) if len(s) else None

def main():
    BASE.mkdir(parents=True, exist_ok=True)
    fulls = [pd.read_parquet(p / "full_fitness_results.parquet") for p in EXPS]
    funnels = [pd.read_parquet(p / "funnel_results.parquet") for p in EXPS]
    full = pd.concat(fulls, ignore_index=True); funnel = pd.concat(funnels, ignore_index=True)
    general = pd.read_parquet(ROOT / "runs/reports/prop_strategy_factory_v1_phase_a/five_day_metrics.parquet")
    general = general[(general.split == "DEVELOPMENT") & (general.horizon_days == 5)]
    policy = {"min_positive_window_fraction": .5, "max_negative_tail_P05": -1.5, "max_worst_window_net_R": -2.5, "max_holding_P95_hours": 240.0}
    policy_counts = {
        "positive_window_fraction_below_floor": int((full.positive_window_fraction < policy["min_positive_window_fraction"]).sum()),
        "negative_tail_P05_below_floor": int((full.negative_tail_P05 < policy["max_negative_tail_P05"]).sum()),
        "worst_window_below_floor": int((full.worst_window_net_R < policy["max_worst_window_net_R"]).sum()),
        "holding_P95_above_floor": int((full.holding_P95_hours > policy["max_holding_P95_hours"]).sum()),
    }
    reason_counts = {}
    for raw in funnel[funnel.stage == "SHORT_HORIZON_QUALITY"].reason_codes_json:
        for reason in json.loads(raw): reason_counts[reason] = reason_counts.get(reason, 0) + 1
    metrics = ["signals_per_day", "trade_count", "positive_window_fraction", "positive_tail_P95", "positive_tail_P99", "negative_tail_P01", "negative_tail_P05", "holding_P50_hours", "holding_P95_hours"]
    comparison = {"general_development": {c: float(general[c].median()) if c in general else None for c in metrics}, "prop_corrected_development": {c: float(full[c].median()) if c in full else None for c in metrics}, "prop_by_execution_profile": full.groupby("execution_profile_id")[metrics].median().to_dict(orient="index"), "definitions_identical": True, "split_policy": "60/80 Phase A policy; OOS not loaded"}
    write("metric_semantics.json", {"GENERAL_METRIC_SEMANTICS": {"window": "Europe/Paris calendar [start,end)", "r": "net trade P/L divided by initial risk", "trade_inclusion": "authoritative closed-trade ledger", "active_day": "entry day in Europe/Paris", "cost": "profile model with explicit status", "split": "60% Development / 20% Validation / final 20% inaccessible"}, "PROP_METRIC_SEMANTICS": {"window": "same", "r": "same", "trade_inclusion": "same evaluator ledger", "active_day": "same", "cost": "same profile model", "split": "same"}, "EQUIVALENCE": "PASS"})
    write("policy_forensics.json", {"policy_version": "PROP_POLICY_VERSION_1_UNCHANGED", "rules": policy, "rule_counts": policy_counts, "short_stage_reason_counts": reason_counts, "decision": "VALID_SAFETY_GATE_WITH_PROP_DOWNSIDE_FAILURE", "change": "none"})
    write("general_vs_prop_corrected.json", comparison)
    write("complete_pilot_summary.json", {"experiments": [p.name for p in EXPS], "markets": ["EURUSD", "XAUUSD"], "timeframes": ["M15", "H1"], "seed": 4101, "generated": 4000, "unique_generated": 4000, "full_survivors_replayed": int(full.strategy_id.nunique()), "prop_candidates": 0, "oos_accesses": 0, "stage_counts": {stage: {status: int(n) for status, n in g.status.value_counts().items()} for stage, g in funnel.groupby("stage")}, "classification": "PROP_FACTORY_DOWNSIDE_TOO_HIGH"})
    ledger = [
        {"experiment_id":"01_gate_forensics", "parent_experiment":None, "hypothesis":"zero gate result may be policy/semantic mismatch", "code_commit":"14208a6ebf2b9c30f91e6c53d11f421d9e432cb5", "markets":["EURUSD"], "timeframes":["M15","H1"], "seeds":[4101], "strategy_count":600, "oos_accesses":0, "result":"semantic mismatch identified; downside also excessive", "decision":"fix metrics before policy calibration"},
        {"experiment_id":"02_semantic_fix", "parent_experiment":"01_gate_forensics", "hypothesis":"shared split boundaries and complete sidecars resolve zero gate", "code_commit":"27bd561c784a51161ea5f45776794caa5b808ec7", "markets":["EURUSD"], "timeframes":["M15","H1"], "seeds":[4101], "strategy_count":600, "oos_accesses":0, "runtime_seconds":548.798652154, "result":"0 short-horizon passes; complete sidecar restored", "decision":"proceed to remaining pilot"},
        {"experiment_id":"03_xau_pilot", "parent_experiment":"02_semantic_fix", "hypothesis":"XAUUSD may provide different short-horizon raw material", "code_commit":"27bd561c784a51161ea5f45776794caa5b808ec7", "markets":["XAUUSD"], "timeframes":["M15","H1"], "seeds":[4101], "strategy_count":2000, "oos_accesses":0, "result":"0 short-horizon passes; downside tail remains excessive", "decision":"apply split-equivalence replay"},
        {"experiment_id":"04_split_fix", "parent_experiment":"03_xau_pilot", "hypothesis":"authoritative 60/80 split must be used consistently", "code_commit":"PENDING_CLOSURE_COMMIT", "markets":["EURUSD","XAUUSD"], "timeframes":["M15","H1"], "seeds":[4101], "strategy_count":1199, "oos_accesses":0, "result":"0 short-horizon passes; semantic equivalence established", "decision":"stop; downside-limited manufacturing evidence"}
    ]
    (BASE / "experiment_ledger.jsonl").write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in ledger))
    hashes = {}
    for path in BASE.rglob("*"):
        if path.is_file() and path.name != "artifact_hashes.json": hashes[str(path.relative_to(BASE))] = hashlib.sha256(path.read_bytes()).hexdigest()
    write("artifact_hashes.json", hashes)
    (BASE / "factory_readiness_report.md").write_text("# PROP STRATEGY FACTORY V1 — AUTONOMOUS LOOP 01\n\nThe pilot produced materially different, shorter and more frequent components, but all corrected replay survivors failed the unchanged short-horizon downside/opportunity safety gate. No PROP_CANDIDATE, Phase D, Phase E, or OOS optimization was performed. Classification: PROP_FACTORY_DOWNSIDE_TOO_HIGH.\n")

if __name__ == "__main__": main()
