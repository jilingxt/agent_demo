from __future__ import annotations

from case_agent_demo.legal_kb import LegalKnowledgeBaseTool
from case_agent_demo.models import ClaimAssessment, EvidenceClaim, EvidenceGraph


def _articles(result):
    return {chunk.article for chunk in result.chunks}


def test_injury_retrieval_excludes_distinct_unalleged_offenses():
    kb = LegalKnowledgeBaseTool()
    result = kb.search(
        "故意伤害类案件 李文杰抱摔贺显作 鼻骨骨折 轻伤二级",
        purpose="legal_basis",
        domain_ids=["criminal_injury", "personal_rights", "public_security_punishment"],
        top_k=12,
    )

    articles = _articles(result)
    assert {"第五十一条", "第二百三十四条"} <= articles
    assert articles.isdisjoint(
        {
            "第二百九十三条",  # 寻衅滋事需要额外的公共秩序/随意性事实
            "第三十条",  # 结伙斗殴、寻衅滋事类治安条款
            "第二百三十九条",  # 绑架
            "第五十条",  # 威胁、侮辱、滋扰
            "第三百零五条",  # 伪证
        }
    )


def test_context_specific_offenses_remain_retrievable_when_alleged():
    kb = LegalKnowledgeBaseTool()
    result = kb.search(
        "多人在公共场所无故随意殴打他人并起哄闹事，破坏社会秩序，寻衅滋事",
        purpose="legal_basis",
        domain_ids=["public_order", "public_security_punishment"],
        top_k=8,
    )

    assert "第二百九十三条" in _articles(result)


def test_denied_or_insufficient_claim_does_not_activate_offense_family():
    kb = LegalKnowledgeBaseTool()
    claim = EvidenceClaim(
        "C-DENY",
        "张三",
        "taking_property",
        object="手机",
        opposing_node_ids=["N-DENY"],
    )
    graph = EvidenceGraph(claims=[claim])
    result = kb.retrieve_for_case(
        "待人工判断案件",
        graph,
        claim_assessments=[ClaimAssessment("C-DENY", status="opposing_dominant")],
    )

    assert "第二百六十四条" not in _articles(result)
    assert "第五十八条" not in _articles(result)
