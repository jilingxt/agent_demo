from __future__ import annotations

from case_agent_demo.legal_kb import LegalKnowledgeBaseTool, _query_from_graph
from case_agent_demo.models import (
    ClaimAssessment,
    EvidenceClaim,
    EvidenceGraph,
    EvidenceNode,
)


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


def test_open_predicate_query_uses_supported_agent_fact_text():
    node = EvidenceNode(
        node_id="N-OPEN",
        node_type="fact",
        source_material_id="M-OPEN",
        source_type="statement",
        summary="系统记录一项待核业务操作",
        behavior="系统记录一项待核业务操作",
        object="测试资金批次A",
        metadata={"legal_query_terms": ["金融机构工作人员 挪用本单位资金"]},
    )
    mapped_node = EvidenceNode(
        node_id="N-MAPPED",
        node_type="fact",
        source_material_id="M-MAPPED",
        source_type="statement",
        summary="另一项受支持事实",
        behavior="另一项受支持事实",
    )
    claim = EvidenceClaim(
        "C-OPEN",
        "测试经办人员",
        "open_domain_conduct",
        object="测试资金批次A",
        supporting_node_ids=[node.node_id],
    )
    mapped_claim = EvidenceClaim(
        "C-MAPPED",
        "测试经办人员",
        "violence",
        supporting_node_ids=[mapped_node.node_id],
    )
    graph = EvidenceGraph(nodes=[node, mapped_node], claims=[claim, mapped_claim])

    query = _query_from_graph(
        "机构业务核查",
        graph,
        [
            ClaimAssessment(claim.claim_id, status="supported"),
            ClaimAssessment(mapped_claim.claim_id, status="supported"),
        ],
    )

    assert "金融机构工作人员 挪用本单位资金" in query


def test_ambiguous_observation_can_supply_candidate_legal_query_terms():
    node = EvidenceNode(
        node_id="N-AMBIGUOUS",
        node_type="fact",
        source_material_id="M-AMBIGUOUS",
        source_type="statement",
        summary="观察者无法完全确认动作",
        behavior="观察者无法完全确认动作",
        polarity="ambiguous",
        metadata={
            "stance": "ambiguous",
            "legal_query_terms": ["公共场所故意裸露身体隐私部位"],
        },
    )
    claim = EvidenceClaim(
        "C-AMBIGUOUS",
        "测试人员",
        "open_observed_conduct",
        ambiguous_node_ids=[node.node_id],
    )

    query = _query_from_graph(
        "行为边界核查",
        EvidenceGraph(nodes=[node], claims=[claim]),
        [ClaimAssessment(claim.claim_id, status="unassessed")],
    )

    assert "公共场所故意裸露身体隐私部位" in query
