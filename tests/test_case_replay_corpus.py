from __future__ import annotations

import json
from pathlib import Path

import pytest

from case_agent_demo.case_replay import discover_cases, load_case, replay_case, validate_replay
from case_agent_demo.workflow import CaseWorkflow
from tests.semantic_runtime import SemanticFixtureRuntime, semantic_fact


ROOT = Path(__file__).resolve().parents[1] / "测试用例"


def _uses_legacy_expectation_schema(case_dir: Path) -> bool:
    config = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    return "expected" in config


CASES = [case_dir for case_dir in discover_cases(ROOT) if _uses_legacy_expectation_schema(case_dir)]


def _semantic_workflow(config):
    materials = config["materials"]
    primary = config["expected"]["primary_claim"]
    model = config["expected"]["bayesian_models"][0]
    facts = {}
    primary_count = int(primary.get("min_sources", 1))
    for item in materials[:primary_count]:
        facts[item["material_id"]] = [
            semantic_fact(
                actor=primary["subject"],
                target_person=primary.get("target", "") if primary["predicate"] != "taking_property" else "",
                object=primary.get("target", "") if primary["predicate"] == "taking_property" else "",
                predicate=primary["predicate"],
                behavior=f"{primary['subject']}的结构化{primary['predicate']}事实",
                stance="affirm",
                event_id=config["case_id"],
                source_group=item["material_id"],
                origin_evidence=item["material_id"],
            )
        ]

    auxiliary = {
        "conduct_result": [
            ("injury_exists" if primary["predicate"] == "violence" else "damage_exists", primary.get("target", ""), "affirm"),
            ("mechanism_consistency", primary.get("target", ""), "affirm"),
            ("temporal_consistency", primary.get("target", ""), "affirm"),
            ("alternative_cause", primary.get("target", ""), "deny"),
        ],
        "property_taking": [
            ("prior_possession", primary.get("target", ""), "affirm"),
            ("possession_transfer", primary.get("target", ""), "affirm"),
            ("property_trace", primary.get("target", ""), "affirm"),
            ("alternative_explanation", primary.get("target", ""), "deny"),
        ],
        "public_order": [
            ("public_context", "", "affirm"),
            ("operational_impact", "", "affirm"),
            ("persistence_or_group", "", "affirm"),
        ],
        "public_safety": [
            ("dangerous_object_or_condition", primary.get("target", ""), "affirm"),
            ("exposure", primary.get("target", ""), "affirm"),
            ("control_failure", primary.get("target", ""), "affirm"),
        ],
        "deception_disposition": [
            ("mistaken_belief", primary.get("target", ""), "affirm"),
            ("property_disposition", primary.get("target", ""), "affirm"),
            ("property_loss", primary.get("target", ""), "affirm"),
        ],
    }[model]
    for predicate, target, stance in auxiliary:
        for item in materials:
            facts.setdefault(item["material_id"], []).append(
                semantic_fact(
                    actor=primary["subject"],
                    target_person=target if predicate not in {"prior_possession"} else "",
                    object=target if predicate in {"prior_possession"} else "",
                    predicate=predicate,
                    behavior=f"结构化{predicate}事实",
                    stance=stance,
                    event_id=config["case_id"],
                    source_group=item["material_id"],
                    origin_evidence=item["material_id"],
                    evidence_category="report_image",
                )
            )
    if model == "deception_disposition":
        item = materials[-1]
        facts[item["material_id"]].append(
            semantic_fact(
                actor=primary["subject"],
                target_person=primary.get("target", ""),
                predicate=primary["predicate"],
                behavior="对同一陈述的结构化否认",
                stance="deny",
                event_id=config["case_id"],
                source_group=item["material_id"],
                origin_evidence=item["material_id"],
            )
        )

    runtime = SemanticFixtureRuntime(facts)
    workflow = CaseWorkflow.demo()
    for agent in (workflow.text_agent, workflow.pic_agent, workflow.report_image_agent):
        agent.runtime = runtime
    return workflow


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_categorized_case_replay_matches_expected_models_and_laws(case_dir):
    config, _ = load_case(case_dir)
    result = replay_case(case_dir, _semantic_workflow(config))
    assert validate_replay(config, result) == []


def test_injury_case_uses_one_multi_source_conduct_claim_and_one_bayesian_run():
    case_dir = ROOT / "故意伤害_多源印证"
    config, _ = load_case(case_dir)
    result = replay_case(case_dir, _semantic_workflow(config))
    claims = [
        claim
        for claim in result.case_graph.claims
        if claim.subject == "李文杰"
        and claim.behavior_type == "violence"
        and claim.target_person == "贺显作"
    ]
    assert len(claims) == 1
    assert len(set(claims[0].supporting_node_ids)) >= 4
    assessment = next(
        item for item in result.claim_assessments if item.claim_id == claims[0].claim_id
    )
    assert assessment.status == "supported"

    runs = [
        run
        for run in result.bayesian_result["runs"]
        if run["model_id"] == "conduct_result"
    ]
    assert len(runs) == 1
    assert runs[0]["derived_values"]["causation"] >= 0.5
