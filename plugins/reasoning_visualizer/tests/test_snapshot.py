from pathlib import Path

from case_agent_demo.cli import sample_materials
from case_agent_demo.workflow import CaseWorkflow
from plugins.reasoning_visualizer.snapshot import build_snapshot, load_snapshot, save_snapshot
from tests.semantic_runtime import SemanticFixtureRuntime, semantic_fact


ROOT = Path(__file__).parents[3]


def _result():
    event_id = "VISUALIZER-DEMO"
    runtime = SemanticFixtureRuntime(
        {
            "S1": [
                semantic_fact(
                    actor="actor-a",
                    target_person="person-b",
                    predicate="violence",
                    behavior="structured conduct assertion",
                    event_id=event_id,
                )
            ],
            "P1": [
                semantic_fact(
                    actor="person-b",
                    target_person="person-b",
                    predicate="injury_exists",
                    behavior="structured result assertion",
                    event_id=event_id,
                    evidence_category="evidence_image",
                ),
                semantic_fact(
                    actor="actor-a",
                    target_person="person-b",
                    predicate="mechanism_consistency",
                    behavior="conduct and result mechanism are consistent",
                    event_id=event_id,
                    evidence_category="evidence_image",
                ),
            ],
            "R1": [
                semantic_fact(
                    actor="actor-a",
                    target_person="person-b",
                    predicate="temporal_consistency",
                    behavior="conduct and result are temporally consistent",
                    event_id=event_id,
                    evidence_category="report_image",
                ),
                semantic_fact(
                    actor="actor-a",
                    target_person="person-b",
                    predicate="alternative_cause",
                    behavior="no alternative cause is supported",
                    stance="deny",
                    event_id=event_id,
                    evidence_category="report_image",
                ),
            ],
        }
    )
    workflow = CaseWorkflow.demo()
    for agent in (workflow.text_agent, workflow.pic_agent, workflow.report_image_agent):
        agent.runtime = runtime
    return workflow.run(sample_materials(), confirmed_case_type="generic conduct case")


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
