from case_agent_demo.evidence_book import EvidenceBookBuilder
from case_agent_demo.evidence_reasoning_engine import EvidenceReasoningEngine
from case_agent_demo.models import CaseGraph, EvidenceNode, LegalMatch


def _node(node_id: str, source_type: str, **metadata) -> EvidenceNode:
    return EvidenceNode(
        node_id=node_id,
        node_type="fact",
        source_material_id=f"M-{node_id}",
        source_type=source_type,
        summary=str(metadata.pop("summary", node_id)),
        time=str(metadata.get("time", "2026年7月1日20时")),
        location=str(metadata.get("location", "深圳市某写字楼")),
        metadata=metadata,
    )


def test_evidence_book_keeps_allegation_defense_and_objective_observation_separate():
    graph = CaseGraph(
        nodes=[
            _node(
                "ALLEGATION",
                "statement",
                summary="王小明称李大海虚构投资项目",
                declarant="王小明",
                declarant_role="reporting_person",
                actor="李大海",
                predicate="deceptive_representation",
                target_person="王小明",
                event_id="EVENT-1",
                stance="affirm",
                assertion_role="allegation",
            ),
            _node(
                "DEFENSE",
                "statement",
                summary="李大海称项目真实，并未欺骗王小明",
                declarant="李大海",
                declarant_role="alleged_actor",
                actor="李大海",
                predicate="deceptive_representation",
                target_person="王小明",
                event_id="EVENT-1",
                stance="deny",
                assertion_role="defense_response",
            ),
            _node(
                "TRANSFER",
                "official_report",
                summary="银行流水显示王小明向李大海转账十万元",
                declarant="银行交易记录",
                actor="王小明",
                predicate="property_disposition",
                object="十万元",
                event_id="EVENT-1",
                stance="affirm",
                assertion_role="evidence_observation",
                evidence_category="transaction_record",
            ),
        ]
    )
    reasoning = EvidenceReasoningEngine().evaluate("", graph)
    graph = CaseGraph(nodes=graph.nodes, claims=reasoning.claims)
    legal_matches = [
        LegalMatch(
            "L-1",
            "中华人民共和国刑法",
            "第二百六十六条",
            "候选条款",
            "虚构项目并转账",
            "test",
        )
    ]

    book = EvidenceBookBuilder().build(
        graph,
        reasoning.assertions,
        reasoning.claim_assessments,
        legal_matches=legal_matches,
        bayesian_result=reasoning.bayesian_result,
    )

    assert [(item.reporter, item.alleged_actor) for item in book.allegations] == [
        ("王小明", "李大海")
    ]
    assert {item.name for item in book.participants} == {"王小明", "李大海"}
    by_name = {item.name: item for item in book.participants}
    assert "reporting_person" in by_name["王小明"].roles
    assert "alleged_actor" in by_name["李大海"].roles
    deceptive = next(item for item in book.fact_findings if item.predicate == "deceptive_representation")
    assert deceptive.supporting_node_ids == ["ALLEGATION"]
    assert deceptive.opposing_node_ids == ["DEFENSE"]
    assert book.objective_circumstances[0].node_id == "TRANSFER"
    assert book.legal_candidates[0].article == "第二百六十六条"
    assert "不代替" in book.conclusion_boundary


def test_unknown_predicate_still_produces_a_dossier_without_bayesian_posterior():
    graph = CaseGraph(
        nodes=[
            _node(
                "UNKNOWN",
                "statement",
                summary="报警人陈某称周某实施一种尚未建模的行为",
                declarant="陈某",
                declarant_role="reporting_person",
                actor="周某",
                predicate="unmodeled_conduct",
                target_person="陈某",
                assertion_role="allegation",
                stance="affirm",
            )
        ]
    )
    reasoning = EvidenceReasoningEngine().evaluate("", graph)
    graph = CaseGraph(nodes=graph.nodes, claims=reasoning.claims)

    book = EvidenceBookBuilder().build(
        graph,
        reasoning.assertions,
        reasoning.claim_assessments,
        bayesian_result=reasoning.bayesian_result,
    )

    assert book.allegations[0].predicate == "unmodeled_conduct"
    assert book.fact_findings[0].status in {"supported", "insufficient"}
    assert reasoning.bayesian_result["runs"] == []
    assert reasoning.bayesian_result["selected_model_ids"] == []
    assert reasoning.bayesian_result["abstentions"][0]["reason"] == (
        "no_matching_relation_component"
    )
    assert book.bayesian_abstentions == reasoning.bayesian_result["abstentions"]


def test_identification_observation_is_exposed_in_the_evidence_book():
    graph = CaseGraph(
        nodes=[
            _node(
                "IDENTIFICATION",
                "evidence_image",
                summary="辨认人陈某从照片组中指认周某",
                declarant="陈某",
                declarant_role="reporting_person",
                actor="陈某",
                target_person="周某",
                predicate="identification",
                stance="affirm",
                assertion_role="evidence_observation",
                evidence_category="identification",
            )
        ]
    )
    reasoning = EvidenceReasoningEngine().evaluate("", graph)
    graph = CaseGraph(nodes=graph.nodes, claims=reasoning.claims)

    book = EvidenceBookBuilder().build(
        graph,
        reasoning.assertions,
        reasoning.claim_assessments,
        bayesian_result=reasoning.bayesian_result,
    )

    assert len(book.identifications) == 1
    assert book.identifications[0].identifier == "陈某"
    assert book.identifications[0].identified_person == "周某"


def test_finding_explains_when_objective_evidence_opposes_an_allegation():
    graph = CaseGraph(
        nodes=[
            _node(
                "ALLEGATION",
                "statement",
                summary="陈某称周某当时在现场",
                declarant="陈某",
                declarant_role="reporting_person",
                actor="周某",
                predicate="presence",
                target_person="现场",
                event_id="EVENT-1",
                stance="affirm",
                assertion_role="allegation",
            ),
            _node(
                "OBJECTIVE-DENIAL",
                "official_report",
                summary="门禁记录显示周某当时不在现场",
                declarant="门禁记录",
                actor="周某",
                predicate="presence",
                target_person="现场",
                event_id="EVENT-1",
                stance="deny",
                assertion_role="evidence_observation",
                evidence_category="access_control_record",
                extraction_quality=1.0,
                relevance=1.0,
                specificity=1.0,
                directness=1.0,
                authenticity=1.0,
                procedural_integrity=1.0,
                internal_consistency=1.0,
                verifiability=1.0,
            ),
        ]
    )
    reasoning = EvidenceReasoningEngine().evaluate("", graph)
    graph = CaseGraph(nodes=graph.nodes, claims=reasoning.claims)

    book = EvidenceBookBuilder().build(
        graph,
        reasoning.assertions,
        reasoning.claim_assessments,
    )
    finding = next(item for item in book.fact_findings if item.predicate == "presence")

    assert finding.status == "objectively_opposed"
    assert "现有客观材料不支持" in finding.conclusion
