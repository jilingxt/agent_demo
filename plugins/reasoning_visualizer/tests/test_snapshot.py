from pathlib import Path

from case_agent_demo.cli import sample_materials
from case_agent_demo.workflow import CaseWorkflow
from plugins.reasoning_visualizer.snapshot import build_snapshot, load_snapshot, save_snapshot


ROOT = Path(__file__).parents[3]


def _result():
    return CaseWorkflow.demo().run(
        sample_materials(),
        confirmed_case_type="盗窃类案件",
    )


def test_snapshot_contains_evidence_reasoning_layers_and_bayesian_runs():
    snapshot = build_snapshot(_result())

    kinds = {node["kind"] for node in snapshot["evidence"]["nodes"]}
    assert {
        "material",
        "fact",
        "assertion",
        "claim",
        "derived_claim",
        "validation_issue",
    }.issubset(kinds)
    assert snapshot["evidence"]["edges"]
    assert snapshot["bayesian"]["runs"]

    run = snapshot["bayesian"]["runs"][0]
    assert run["model_id"] == "conduct_result"
    assert run["anchor_claim_id"]
    assert run["nodes"]
    assert run["edges"]
    assert any(node["role"] == "derived" for node in run["nodes"])
    assert any(node["calculation"]["formula"].startswith("sigmoid") for node in run["nodes"])


def test_snapshot_round_trip(tmp_path):
    snapshot = build_snapshot(_result())
    path = save_snapshot(snapshot, tmp_path / "case.snapshot.json")

    assert load_snapshot(path) == snapshot


def test_main_package_does_not_import_visualizer_plugin():
    core_files = (ROOT / "case_agent_demo").glob("*.py")
    offenders = [
        path.name
        for path in core_files
        if "plugins.reasoning_visualizer" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
