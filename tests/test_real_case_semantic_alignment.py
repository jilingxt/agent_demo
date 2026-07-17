from __future__ import annotations

from dataclasses import asdict

from case_agent_demo.agents import ReportImageAgent, TextAgent
from case_agent_demo.evidence_reasoning_engine import EvidenceReasoningEngine
from case_agent_demo.graph_store import GraphStoreTool
from case_agent_demo.models import Material, MaterialType
from case_agent_demo.agents import EvidenceGraphAgent
from tests.semantic_runtime import SemanticFixtureRuntime, semantic_fact


VICTIM_STATEMENT = """
被询问人贺显作。事件编号：CASE-INJURY-001。
2026年6月12日17时许，在深圳市宝安区新凯飞汽配，李文杰拉住我的衣领将我拽倒，
之后我们互相推搡，李文杰又将我抱摔在地，我的鼻部当场流血。
"""

ACTOR_STATEMENT = """
被询问人李文杰。事件编号：CASE-INJURY-001。
2026年6月12日17时许，在深圳市宝安区新凯飞汽配，我拉住贺显作衣领将其拽倒，
后将贺显作抱摔在地。贺显作鼻部流血是我抱摔造成的。
"""

VIDEO_REPORT = """
监控研判报告。事件编号：CASE-INJURY-001。
监控显示李文杰拉拽贺显作衣领并将其拽倒，约五秒后又将贺显作抱摔在地，
贺显作随即捂住鼻部并出现流血。
"""

FORENSIC_REPORT = """
法医鉴定意见书。事件编号：CASE-INJURY-001。被鉴定人贺显作。
鉴定意见：鼻骨骨折，损伤程度达到轻伤二级；该损伤形成机制与钝性外力作用相吻合。
"""


def _reasoning_result():
    materials = [
        Material("S-VICTIM", MaterialType.STATEMENT, VICTIM_STATEMENT),
        Material("S-ACTOR", MaterialType.STATEMENT, ACTOR_STATEMENT),
        Material("R-VIDEO", MaterialType.REPORT_IMAGE, VIDEO_REPORT),
        Material("R-FORENSIC", MaterialType.REPORT_IMAGE, FORENSIC_REPORT),
    ]
    store = GraphStoreTool()
    graph_agent = EvidenceGraphAgent()
    runtime = SemanticFixtureRuntime(
        {
            "S-VICTIM": [semantic_fact(actor="李文杰", target_person="贺显作", predicate="violence", behavior="李文杰对贺显作实施暴力行为", declarant="贺显作", event_id="CASE-INJURY-001", fact_id="F-S-VICTIM-TEXT")],
            "S-ACTOR": [semantic_fact(actor="李文杰", target_person="贺显作", predicate="violence", behavior="李文杰陈述其对贺显作实施暴力行为", declarant="李文杰", event_id="CASE-INJURY-001", fact_id="F-S-ACTOR-TEXT")],
            "R-VIDEO": [
                semantic_fact(actor="李文杰", target_person="贺显作", predicate="violence", behavior="视频记录李文杰对贺显作实施暴力行为", event_id="CASE-INJURY-001", fact_id="F-R-VIDEO-REPORT", evidence_category="report_image"),
                semantic_fact(actor="李文杰", target_person="贺显作", predicate="temporal_consistency", behavior="行为与结果在时间上相邻", event_id="CASE-INJURY-001", evidence_category="report_image"),
            ],
            "R-FORENSIC": [
                semantic_fact(actor="贺显作", target_person="贺显作", predicate="injury_grade", behavior="贺显作的损伤被评定为轻伤二级", event_id="CASE-INJURY-001", evidence_category="report_image"),
                semantic_fact(actor="贺显作", target_person="贺显作", predicate="injury_exists", behavior="贺显作存在损伤", event_id="CASE-INJURY-001", evidence_category="report_image"),
                semantic_fact(actor="李文杰", target_person="贺显作", predicate="mechanism_consistency", behavior="行为方式与损伤机制相符", event_id="CASE-INJURY-001", evidence_category="report_image"),
            ],
        }
    )
    for material in materials:
        agent = TextAgent(runtime=runtime) if material.material_type == MaterialType.STATEMENT else ReportImageAgent(runtime=runtime)
        for fact in agent.extract(material):
            graph_agent.add_fact(store, fact)
    verification = {
        "R-FORENSIC": {
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
    }
    return EvidenceReasoningEngine().evaluate(
        "故意伤害类案件",
        store.to_graph(),
        authority_verifications=verification,
    )


def test_three_independent_descriptions_of_same_conduct_form_one_claim():
    result = _reasoning_result()
    claims = [
        claim
        for claim in result.claims
        if claim.behavior_type == "violence"
        and claim.subject == "李文杰"
        and claim.target_person == "贺显作"
    ]

    assert len(claims) == 1
    claim = claims[0]
    assert set(claim.supporting_node_ids) >= {
        "F-S-VICTIM-TEXT",
        "F-S-ACTOR-TEXT",
        "F-R-VIDEO-REPORT",
    }
    assessment = next(item for item in result.claim_assessments if item.claim_id == claim.claim_id)
    assert assessment.status == "supported", asdict(assessment)


def test_verified_forensic_result_joins_same_event_bayesian_run():
    result = _reasoning_result()
    injury = next(claim for claim in result.claims if claim.behavior_type == "injury_grade")
    injury_assessment = next(
        item for item in result.claim_assessments if item.claim_id == injury.claim_id
    )
    assert injury_assessment.status == "authority_anchored"

    runs = result.bayesian_result["runs"]
    conduct_runs = [run for run in runs if run["model_id"] == "conduct_result"]
    assert len(conduct_runs) == 1
    assert {"conduct", "result_exists"} <= set(conduct_runs[0]["soft_evidence"])
    assert conduct_runs[0]["derived_values"]["causation"] >= 0.5
