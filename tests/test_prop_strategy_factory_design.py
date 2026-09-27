import json
from pathlib import Path


DOCS = Path("docs/prop_strategy_factory_v1")
REPORT = Path("runs/reports/prop_strategy_factory_v1_design")


def test_prop_factory_design_artifacts_are_complete_and_valid_json():
    required_docs = {
        "architecture.md", "component_reuse_matrix.md", "prop_metrics.md",
        "prop_fitness.md", "prop_grammar.md", "prop_exit_grammar.md",
        "promotion_funnel.md", "strategy_library_contract.md", "portfolio_handoff.md",
        "ab_experiment.md", "implementation_plan.md", "repository_changes.md", "versioning.md",
    }
    assert required_docs.issubset({p.name for p in DOCS.glob("*.md")})
    json_files = list(REPORT.glob("*.json"))
    assert len(json_files) >= 7
    for path in json_files:
        json.loads(path.read_text())


def test_prop_design_preserves_existing_lineage_and_is_design_only():
    manifest = json.loads((REPORT / "design_manifest.json").read_text())
    assert manifest["status"] == "DESIGN_ONLY"
    assert manifest["existing_prop_ready"] == 8438
    assert manifest["strategy_logic_modified"] is False
    assert manifest["mql5_logic_modified"] is False
