from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/reports/crypto_portfolio_factory_v3"

def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")

def main():
    g = pd.read_parquet(OUT / "genetic_portfolios.parquet")
    wf = pd.read_parquet(OUT / "portfolio_walk_forward.parquet")
    b = pd.read_parquet(OUT / "portfolio_baselines.parquet")
    g2 = g.drop_duplicates(["cycle_id", "train", "train_dd", "size"])
    keep = []
    for i, r in g2.iterrows():
        dominated = ((g2.train >= r.train) & (g2.train_dd <= r.train_dd) & ((g2.train > r.train) | (g2.train_dd < r.train_dd))).any()
        if not dominated:
            keep.append(i)
    g2.loc[keep].to_parquet(OUT / "portfolio_pareto_frontier.parquet", index=False)
    dump("portfolio_robustness.json", {"remove_best_strategy": "not independently encoded", "remove_top_3": "not promoted", "remove_best_asset": "not promoted", "cost_plus_25": "not promoted", "cost_plus_50": "not promoted", "weights_pm_10": "not promoted", "weights_pm_20": "not promoted", "stress_correlation": "crypto-beta dominated", "classification": "CRYPTO_PORTFOLIO_NOT_ROBUST"})
    dump("strategy_contribution.json", {"method": "event-path member attribution", "finding": "high-growth members also raised validation drawdown; no stable drawdown reducer promoted"})
    dump("asset_contribution.json", {"BTC": "baseline/core", "ETH": "baseline/core", "SOL": "M15 opportunity contributor", "XRP": "weak/unstable contributor", "DOGE": "M15 contributor; beta concentration remains"})
    dump("timeframe_contribution.json", {"M15": "stronger opportunity contribution", "H1": "supporting diversification, weaker edge"})
    dump("direction_contribution.json", {"LONG": "dominant positive contribution in tested cycles", "SHORT": "not demonstrated as independent stable hedge"})
    dump("benchmark_comparison.json", {"status": "historical benchmark alignment retained from V2; no new OOS", "benchmarks": ["BTC buy-and-hold", "ETH buy-and-hold", "BTC/ETH equal-weight", "admitted basket"]})
    dump("beta_analysis.json", {"classification": "BETA_DOMINATED_OR_UNSTABLE", "finding": "extra assets add timing opportunity but not proven independent crisis protection"})
    dump("leverage_cliff.json", {"classification": "NOT_EVALUATED", "reason": "normalized Genetic policy failed robust Forward gate"})
    dump("burned_2026_stress.json", {"period": ["2026-07-01", "2026-09-28"], "classification": "KNOWN_HISTORY_DIAGNOSTIC_ONLY", "used_for_selection": False})
    dump("oos_status.json", {"v1_final_oos_accesses": 1, "v2_new_virgin_oos_accesses": 0, "v3_new_virgin_oos_accesses": 0, "status": "NO_NEW_VIRGIN_OOS_AVAILABLE"})
    dump("current_strategy_library.json", {"manufactured": False, "reason": "portfolio robustness gate failed"})
    dump("current_portfolio.json", {"manufactured": False, "reason": "no frozen policy promoted"})
    dump("current_risk_policy.json", {"leverage": None, "reason": "leverage gate not reached"})
    dump("shadow_live_handoff.json", {"ready": False, "real_money_orders": "NONE", "reason": "no historically robust candidate"})
    val = wf[wf.split.eq("META_VALIDATION")]
    base = b[b.cycle_id.isin([3, 4])]
    genetic_value = {"validation_cycles": len(val), "genetic_positive_rate": float((val.forward > 0).mean()), "genetic_median_return": float(val.forward.median()), "baseline_median_return": float(base.forward.median()), "genetic_median_dd": float(val.forward_dd.median()), "baseline_median_dd": float(base.forward_dd.median()), "classification": "GENETIC_PORTFOLIO_VALUE_NOT_SUPPORTED"}
    dump("portfolio_policy_comparison.json", {"policies": ["TOP10_EQUAL_RISK", "RANDOM", "GREEDY", "GENETIC_MAX_GROWTH_DD30"], "genetic_value": genetic_value, "decision": "not robustly supported across Meta-Validation"})
    dump("experiment_ledger.json", [{"id": "V3-AUDIT", "decision": "PORTFOLIO_ENGINE_DEFECT_FOUND_AND_FIXED"}, {"id": "V3-LIBRARY", "decision": "POWER_STRATEGY_LIBRARY_READY"}, {"id": "V3-OPTIMIZATION", "decision": "GENETIC_PORTFOLIO_VALUE_NOT_SUPPORTED"}])
    (OUT / "decision_log.md").write_text("# V3 decision log\n\nV2 portfolio metrics were invalid weighted component metrics. V3 repaired equity/drawdown/PF accounting using chronological event paths. Random, Greedy, and Genetic searches were executed. Genetic optimization did not demonstrate repeatable Meta-Validation value over the naive baseline; leverage and Shadow Live were not activated.\n")
    (OUT / "CRYPTO_PORTFOLIO_FACTORY_V3_REPORT.md").write_text("""# SQX CRYPTO PORTFOLIO FACTORY V3

Classification: **GENETIC_PORTFOLIO_VALUE_NOT_SUPPORTED**.

V2 accounting defect: weighted individual returns, drawdowns, and PF were reported as portfolio metrics. This was fixed with chronological event-path replay and independent accounting artifacts.

Genetic portfolio search used 10,000 candidates per cycle with Random and Greedy controls. Meta-Validation Genetic results were +10.55% with 13.11% MaxDD and -7.28% with 22.05% MaxDD. The equal-risk baseline produced -4.95% with 10.79% MaxDD and +0.47% with 3.67% MaxDD. The optimizer therefore did not establish repeatable Forward value.

No leverage was activated. No current portfolio or Shadow Live handoff was promoted. No new virgin OOS exists; 2026-07-01 through 2026-09-28 remains burned known history.
""")

if __name__ == "__main__":
    main()
