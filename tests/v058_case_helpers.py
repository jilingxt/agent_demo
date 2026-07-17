from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from case_agent_demo.evidence_intake import _extract_docx_text
from case_agent_demo.models import Material, MaterialType, WorkflowResult
from case_agent_demo.workflow import CaseWorkflow
from tests.semantic_runtime import SemanticFixtureRuntime


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "测试用例" / "v058随机条文"


def discover_v058_cases(root: Path = CORPUS_ROOT) -> list[Path]:
    return sorted(path.parent for path in root.glob("*/case.json"))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_case_materials(case_dir: Path) -> tuple[dict[str, Any], list[Material]]:
    config = load_json(case_dir / "case.json")
    materials = []
    for item in config["materials"]:
        source_path = case_dir / item["path"]
        materials.append(
            Material(
                material_id=str(item["material_id"]),
                material_type=MaterialType(str(item["material_type"])),
                content=_extract_docx_text(source_path),
                source_path=str(source_path.resolve()),
                metadata={"title": item["title"], "role": item["role"]},
            )
        )
    return config, materials


def build_semantic_workflow(case_dir: Path) -> CaseWorkflow:
    semantic = load_json(case_dir / "expected" / "semantic_assertions.json")
    facts_by_material: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in semantic["assertions"]:
        facts_by_material[str(item["source_material_id"])].append(
            dict(item["agent_fact"])
        )

    runtime = SemanticFixtureRuntime(dict(facts_by_material))
    workflow = CaseWorkflow.demo()
    for agent in (
        workflow.text_agent,
        workflow.pic_agent,
        workflow.report_image_agent,
    ):
        agent.runtime = runtime
    return workflow


def replay_v058_case(case_dir: Path) -> WorkflowResult:
    config, materials = load_case_materials(case_dir)
    workflow = build_semantic_workflow(case_dir)
    return workflow.run(
        materials,
        confirmed_case_type=str(config["case_type"]),
        authority_verifications=config.get("authority_verifications"),
    )


def assert_expected_outcome(case_dir: Path, result: WorkflowResult) -> None:
    expected = load_json(case_dir / "expected" / "expected_outcome.json")
    case_id = str(expected["case_id"])
    claims = result.case_graph.claims
    assessments = {item.claim_id: item for item in result.claim_assessments}

    for required in expected["required_claims"]:
        candidates = [claim for claim in claims if _claim_matches(claim, required)]
        assert len(candidates) == 1, (
            f"{case_id}: expected one claim {required}, got "
            f"{[_claim_projection(item) for item in candidates]}"
        )
        assessment = assessments.get(candidates[0].claim_id)
        assert assessment is not None, f"{case_id}: missing assessment for {candidates[0].claim_id}"
        assert assessment.status == required["status"], (
            f"{case_id}: claim {_claim_projection(candidates[0])} status "
            f"{assessment.status!r}, expected {required['status']!r}; "
            f"opinion={assessment.opinion}; reasons={assessment.reasons}"
        )

    for forbidden in expected["forbidden_claims"]:
        assert not any(_claim_matches(claim, forbidden) for claim in claims), (
            f"{case_id}: forbidden claim appeared: {forbidden}"
        )

    bayesian = result.bayesian_result or {}
    assert set(expected["expected_bayesian_models"]).issubset(
        set(bayesian.get("selected_model_ids", []))
    ), (
        f"{case_id}: selected Bayesian models={bayesian.get('selected_model_ids', [])}, "
        f"expected={expected['expected_bayesian_models']}"
    )
    if expected["expected_abstention"]:
        assert bayesian.get("abstentions"), f"{case_id}: expected an audited abstention"

    articles = {item.article for item in result.legal_matches}
    assert set(expected["required_legal_articles"]).issubset(articles), (
        f"{case_id}: retrieved articles={sorted(articles)}, "
        f"required={expected['required_legal_articles']}"
    )

    issue_types = {item.issue_type for item in result.validation_issues}
    assert set(expected["required_issue_types"]).issubset(issue_types), (
        f"{case_id}: validation issues={sorted(issue_types)}, "
        f"required={expected['required_issue_types']}"
    )
    for phrase in expected["forbidden_final_conclusions"]:
        assert phrase not in result.final_report, (
            f"{case_id}: final report contains forbidden conclusion {phrase!r}"
        )


def _claim_matches(claim: object, contract: dict[str, Any]) -> bool:
    return (
        getattr(claim, "subject") == contract.get("actor", "")
        and getattr(claim, "behavior_type") == contract.get("predicate", "")
        and getattr(claim, "target_person") == contract.get("target_person", "")
        and getattr(claim, "object") == contract.get("object", "")
    )


def _claim_projection(claim: object) -> dict[str, str]:
    return {
        "actor": str(getattr(claim, "subject")),
        "predicate": str(getattr(claim, "behavior_type")),
        "target_person": str(getattr(claim, "target_person")),
        "object": str(getattr(claim, "object")),
        "event_id": str(getattr(claim, "event_id")),
    }
