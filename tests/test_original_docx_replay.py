from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from case_agent_demo.models import Material, MaterialType
from case_agent_demo.workflow import CaseWorkflow
from tests.semantic_runtime import SemanticFixtureRuntime, semantic_fact


ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = ROOT / "测试用例"
REFERENCE_ROOT = CASE_ROOT / "伤害"


def _docx_text(path: Path) -> str:
    with ZipFile(path) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    return "\n".join(
        "".join(item.text or "" for item in paragraph.iter(namespace + "t"))
        for paragraph in document.iter(namespace + "p")
    )


def test_original_docx_materials_no_longer_report_primary_evidence_insufficiency():
    forensic = (
        CASE_ROOT / "故意伤害_多源印证" / "reports" / "法医鉴定意见.txt"
    ).read_text(encoding="utf-8").replace("事件编号：CASE-INJURY-001。", "")
    materials = [
        Material("S-HE", MaterialType.STATEMENT, _docx_text(REFERENCE_ROOT / "test_he.docx")),
        Material("S-LI", MaterialType.STATEMENT, _docx_text(REFERENCE_ROOT / "test_li.docx")),
        Material("R-VIDEO", MaterialType.REPORT_IMAGE, _docx_text(REFERENCE_ROOT / "video_report.docx")),
        Material("R-FORENSIC", MaterialType.REPORT_IMAGE, forensic),
    ]
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

    runtime = SemanticFixtureRuntime(
        {
            "S-HE": [semantic_fact(actor="李文杰", target_person="贺显作", predicate="violence", behavior="李文杰对贺显作实施暴力行为", declarant="贺显作", event_id="CASE-INJURY-001")],
            "S-LI": [semantic_fact(actor="李文杰", target_person="贺显作", predicate="violence", behavior="李文杰陈述其实施暴力行为", declarant="李文杰", event_id="CASE-INJURY-001")],
            "R-VIDEO": [
                semantic_fact(actor="李文杰", target_person="贺显作", predicate="violence", behavior="视频记录相关暴力行为", event_id="CASE-INJURY-001", evidence_category="report_image"),
                semantic_fact(actor="李文杰", target_person="贺显作", predicate="temporal_consistency", behavior="行为与结果时间相邻", event_id="CASE-INJURY-001", evidence_category="report_image"),
            ],
            "R-FORENSIC": [
                semantic_fact(actor="贺显作", target_person="贺显作", predicate="injury_grade", behavior="损伤被评定为轻伤二级", event_id="CASE-INJURY-001", evidence_category="report_image"),
                semantic_fact(actor="李文杰", target_person="贺显作", predicate="mechanism_consistency", behavior="行为方式与损伤机制相符", event_id="CASE-INJURY-001", evidence_category="report_image"),
            ],
        }
    )
    workflow = CaseWorkflow.demo()
    workflow.text_agent.runtime = runtime
    workflow.report_image_agent.runtime = runtime

    result = workflow.run(
        materials,
        "故意伤害类案件",
        authority_verifications=verification,
    )
    violence = next(
        claim
        for claim in result.case_graph.claims
        if claim.subject == "李文杰"
        and claim.behavior_type == "violence"
        and claim.target_person == "贺显作"
    )
    assessment = next(
        item for item in result.claim_assessments if item.claim_id == violence.claim_id
    )

    assert len(set(violence.supporting_node_ids)) == 3
    assert assessment.status == "supported"
    assert [run["model_id"] for run in result.bayesian_result["runs"]] == ["conduct_result"]
    assert result.bayesian_result["runs"][0]["derived_values"]["causation"] >= 0.5
    assert {(item.law_name, item.article) for item in result.legal_matches} == {
        ("中华人民共和国刑法", "第二百三十四条"),
        ("中华人民共和国治安管理处罚法", "第五十一条"),
    }
    assert not any(issue.issue_type == "evidence_insufficiency" for issue in result.validation_issues)
