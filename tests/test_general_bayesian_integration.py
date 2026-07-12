from case_agent_demo.evidence_reasoning_engine import EvidenceReasoningEngine
from case_agent_demo.final_conflict_agent import FinalConflictAgent
from case_agent_demo.models import EvidenceGraph, EvidenceNode, LegalRAGResult


def _node(
    node_id: str,
    predicate: str,
    *,
    value: float = 0.9,
    actor: str = "行为人",
    target: str = "相对人",
) -> EvidenceNode:
    return EvidenceNode(
        node_id=node_id,
        node_type="fact",
        source_material_id=node_id,
        source_type="statement",
        summary=predicate,
        person=actor,
        behavior=predicate,
        confidence=value,
        metadata={
            "actor": actor,
            "target_person": target,
            "predicate": predicate,
            "event_id": "EVENT-1",
            "stance": "affirm",
            "source_group": node_id,
            "origin_evidence": node_id,
        },
    )


def test_injury_scenario_uses_general_conduct_result_model():
    graph = EvidenceGraph(
        nodes=[
            _node("N-CONDUCT", "violence"),
            _node("N-RESULT", "injury_exists"),
            _node("N-MECHANISM", "mechanism_compatible"),
            _node("N-TIME", "temporal_proximity"),
        ]
    )

    result = EvidenceReasoningEngine().evaluate("故意伤害", graph)

    assert result.bayesian_result["selected_model_ids"] == ["conduct_result"]
    assert result.model_versions["bayesian"] == "conduct_result:1"
    assert result.model_versions["bayesian_models"] == ["conduct_result:1"]
    assert "intentional_injury" not in str(result.bayesian_result)
    assert any(claim.behavior_type == "causation" for claim in result.claims)


def test_mixed_case_can_run_multiple_equal_priority_models():
    graph = EvidenceGraph(
        nodes=[
            _node("N-CONDUCT", "property_damage"),
            _node("N-RESULT", "damage_exists"),
            _node("N-POSSESSION", "prior_possession"),
            _node("N-TAKING", "taking_property"),
            _node("N-TRANSFER", "possession_transfer"),
        ]
    )

    result = EvidenceReasoningEngine().evaluate("财产权益相关案件", graph)

    assert result.bayesian_result["selected_model_ids"] == [
        "conduct_result",
        "property_taking",
    ]
    assert result.bayesian_result["parameter_hash"] not in {
        run["parameter_hash"] for run in result.bayesian_result["runs"]
    }
    assert all(":" in key for key in result.bayesian_result["soft_evidence"])
    assert {claim.behavior_type for claim in result.claims}.issuperset(
        {"causation", "taking_supported"}
    )


def test_generic_derived_fact_can_trigger_final_review_without_case_special_case():
    graph = EvidenceGraph(nodes=[_node("N-ORDER", "public_order_conduct")])
    reasoning = EvidenceReasoningEngine().evaluate("扰乱公共秩序", graph)
    reviewed_graph = EvidenceGraph(nodes=graph.nodes, claims=reasoning.claims)
    rag = LegalRAGResult(matches=[], chunks=[], query="", purpose="review")

    issues = FinalConflictAgent().review(
        "扰乱公共秩序",
        reviewed_graph,
        "",
        rag,
        claim_assessments=reasoning.claim_assessments,
        bayesian_result=reasoning.bayesian_result,
    )

    assert any(issue.issue_type == "derived_fact_insufficient" for issue in issues)
    assert all("故意伤害" not in issue.reason for issue in issues)


def test_derived_claim_uses_anchor_actor_even_when_result_claim_comes_first():
    graph = EvidenceGraph(nodes=[
        _node("N-RESULT", "injury_exists", actor="受害人", target="受害人"),
        _node("N-CONDUCT", "violence", actor="行为人", target="受害人"),
    ])

    result = EvidenceReasoningEngine().evaluate("人身权益案件", graph)
    causation = next(claim for claim in result.claims if claim.behavior_type == "causation")

    assert causation.subject == "行为人"
    assert causation.target_person == "受害人"
