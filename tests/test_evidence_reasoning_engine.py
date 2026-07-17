from case_agent_demo.agents import ReasoningAgent
from case_agent_demo.evidence_reasoning_engine import EvidenceReasoningEngine
from case_agent_demo.models import EvidenceGraph, EvidenceNode, infer_polarity


def _node(node_id: str, *, predicate: str, stance: str = "affirm", authority=None):
    metadata = {
        "actor": "张三" if predicate not in {"injury_exists", "injury_grade"} else "李四",
        "target_person": "李四",
        "predicate": predicate,
        "event_id": "EVENT-1",
        "stance": stance,
        "source_group": node_id,
        "origin_evidence": node_id,
    }
    if authority is not None:
        metadata["authority"] = authority
    return EvidenceNode(
        node_id=node_id,
        node_type="fact",
        source_material_id=node_id,
        source_type="statement" if authority is None else "forensic_report",
        summary=predicate,
        person=metadata["actor"],
        behavior=predicate,
        confidence=0.9,
        metadata=metadata,
    )


def _verified_forensic_authority():
    return {
        "issuer": "qualified_forensic_institution",
        "document_type": "forensic_injury_grade_report",
        "competence_verified": True,
        "authenticity_verified": True,
        "procedure_verified": True,
        "subject_identity_verified": True,
        "method_verified": True,
        "standard_verified": True,
        "scope_verified": True,
        "human_verified": True,
    }


def test_property_damage_uses_general_conduct_result_template():
    graph = EvidenceGraph(nodes=[_node("N-DAMAGE", predicate="property_damage")])

    result = EvidenceReasoningEngine().evaluate("故意毁坏财物", graph)

    assert result.claim_assessments
    assert result.bayesian_result["selected_model_ids"] == ["conduct_result"]
    assert result.model_versions["subjective"] == "subjective-evidence-v1"


def test_conduct_result_scenario_combines_subjective_authority_and_bayesian_layers():
    graph = EvidenceGraph(
        nodes=[
            _node("N-PRESENT", predicate="presence"),
            _node("N-CONTACT", predicate="physical_contact"),
            _node("N-VICTIM", predicate="violence"),
            _node("N-DENIAL", predicate="violence", stance="deny"),
            _node("N-INJURY-EXISTS", predicate="injury_exists"),
            _node("N-INJURY", predicate="injury_grade", authority=_verified_forensic_authority()),
            _node("N-MECHANISM", predicate="mechanism_compatible"),
            _node("N-TIME", predicate="temporal_proximity"),
        ]
    )

    result = EvidenceReasoningEngine().evaluate("故意伤害", graph)
    assessments = {item.claim_id: item for item in result.claim_assessments}
    claims = {claim.behavior_type: claim for claim in result.claims}

    assert assessments[claims["violence"].claim_id].status == "contested"
    assert assessments[claims["injury_grade"].claim_id].status == "authority_anchored"
    assert result.bayesian_result["node_values"]["causation"] > 0.5
    assert assessments[claims["violence"].claim_id].status == "contested"
    assert result.model_versions["bayesian"] == "conduct_result:1"
    assert result.model_versions["bayesian_models"] == ["conduct_result:1"]
    causation = assessments[claims["causation"].claim_id]
    assert causation.status == "bayesian_derived"
    assert causation.bayesian_posterior == round(result.bayesian_result["node_values"]["causation"], 4)
    assert result.bayesian_result["soft_evidence_sources"]["conduct"]


def test_reasoning_report_marks_contested_claims_in_place():
    graph = EvidenceGraph(
        nodes=[
            _node("N-SUPPORT", predicate="violence"),
            _node("N-OPPOSE", predicate="violence", stance="deny"),
        ]
    )
    result = EvidenceReasoningEngine().evaluate("故意伤害", graph)
    assessed_graph = EvidenceGraph(nodes=graph.nodes, claims=result.claims)

    report = ReasoningAgent().reason(
        {
            "confirmed_case_type": "故意伤害",
            "evidence_graph": assessed_graph,
            "claim_assessments": result.claim_assessments,
            "bayesian_result": result.bayesian_result,
            "legal_matches": [],
            "conflicts": [],
        }
    )

    assert "争议材料（尚不能作为确定事实）" in report


def test_unrelated_use_of_character_wei_is_not_a_denial():
    assert infer_polarity("张三是未成年人") == "ambiguous"
    assert infer_polarity("张三未实施殴打") == "ambiguous"
