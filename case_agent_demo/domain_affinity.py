from __future__ import annotations

from dataclasses import replace

from case_agent_demo.models import DomainAffinity, EvidenceGraph, LegalChunk, LegalDocument, LegalDomain


DEFAULT_LEGAL_DOMAINS = [
    LegalDomain("personal_rights", "人身权益", keywords=["伤害", "殴打", "人身", "损伤", "伤情"]),
    LegalDomain("property_rights", "财产权益", keywords=["财物", "占有", "拿走", "盗窃", "损坏", "转账", "损失"]),
    LegalDomain("deception_disposition", "欺骗与财产处分", keywords=["虚构", "隐瞒真相", "欺骗", "错误认识", "转账", "财产处分", "损失"]),
    LegalDomain("economic_transactions", "经济交易事实", keywords=["投资", "合同", "交易", "付款", "转账", "账户"]),
    LegalDomain("public_order", "公共秩序", keywords=["公共秩序", "扰乱", "起哄", "聚众", "场所秩序"]),
    LegalDomain("public_safety", "公共安全", keywords=["公共安全", "危险物质", "危险状态", "暴露", "失控"]),
    LegalDomain("social_management", "社会管理", keywords=["许可证", "资格", "义务", "无证", "未经许可"]),
    LegalDomain("status_duty", "特定身份与义务", keywords=["特定身份", "法定义务", "职责", "授权", "资格"]),
    LegalDomain("criminal_injury", "伤害与损伤", keywords=["故意伤害", "殴打", "轻伤", "重伤", "伤情", "他人身体"]),
    LegalDomain("property_damage", "财物损坏", keywords=["故意毁坏", "毁坏", "损坏", "财物", "价格认定"]),
    LegalDomain("theft", "财物取得", keywords=["盗窃", "窃取", "非法占有", "扒窃", "拿走"]),
    LegalDomain("public_security_punishment", "治安管理处罚", keywords=["治安管理", "处罚", "拘留", "罚款"]),
    LegalDomain("procedure_compliance", "办案程序规范", keywords=["程序", "告知", "询问", "扣押", "调取", "送达", "办案"]),
    LegalDomain("evidence_review", "证据审查", keywords=["证据", "证明", "真实性", "关联性", "合法性", "审查"]),
    LegalDomain("forensic_injury", "伤情鉴定", keywords=["鉴定", "伤情", "轻伤二级", "人体损伤", "鉴定意见"]),
    LegalDomain("image_video_evidence", "图片与视听资料", keywords=["图片", "监控", "视频", "视听资料", "照片"]),
    LegalDomain("identification", "辨认", keywords=["辨认", "辨认笔录", "照片辨认"]),
    LegalDomain("statement_review", "笔录与证言审查", keywords=["询问", "笔录", "证人证言", "讯问"]),
    LegalDomain("supplementary_investigation", "补充调查与补证", keywords=["补充侦查", "补证", "补充调取", "补充询问"]),
    LegalDomain("report_boundary", "报告边界", keywords=["辅助分析", "不得", "最终结论", "边界"]),
]


class DomainAffinityIndexer:
    def __init__(self, domains: list[LegalDomain] | None = None) -> None:
        self.domains = domains or DEFAULT_LEGAL_DOMAINS

    def score_text(
        self,
        text: str,
        manual_affinities: dict[str, float] | None = None,
    ) -> list[DomainAffinity]:
        affinities: list[DomainAffinity] = []
        for domain in self.domains:
            hits = sum(1 for keyword in domain.keywords if keyword in text)
            manual = (manual_affinities or {}).get(domain.domain_id)
            keyword_score = min(1.0, hits / max(1, min(3, len(domain.keywords))))
            score = 0.60 * manual + 0.40 * keyword_score if manual is not None else keyword_score
            if score > 0:
                affinities.append(
                    DomainAffinity(
                        domain.domain_id,
                        round(score, 4),
                        "keyword",
                        f"命中 {hits} 个领域关键词",
                    )
                )
        return sorted(affinities, key=lambda item: item.score, reverse=True)

    def score_document(
        self,
        document: LegalDocument,
        chunks: list[LegalChunk],
    ) -> list[DomainAffinity]:
        text = " ".join([document.title, *[chunk.text for chunk in chunks]])
        return self.score_text(text)

    def score_chunk(self, chunk: LegalChunk) -> list[DomainAffinity]:
        return self.score_text(f"{chunk.title} {chunk.article} {chunk.text}")


class CaseDomainRouter:
    def infer_domains(self, case_type: str, evidence_graph: EvidenceGraph) -> list[DomainAffinity]:
        del case_type
        from case_agent_demo.bayesian_tool import BayesianModelRegistry

        predicates = {
            claim.behavior_type
            for claim in evidence_graph.claims
            if claim.behavior_type and claim.behavior_type != "unresolved_observation"
        }
        predicates.update(
            node.claim_type
            for node in evidence_graph.nodes
            if node.claim_type and node.claim_type != "unresolved_observation"
        )
        affinities: dict[str, DomainAffinity] = {}
        for model in BayesianModelRegistry().models:
            if not predicates.intersection(model.trigger_predicates):
                continue
            for domain_id in model.domains:
                _upsert_affinity(
                    affinities,
                    domain_id,
                    0.90,
                    "predicate_registry",
                    f"结构化谓词命中贝叶斯关系组件 {model.model_id}",
                )

        source_types = {node.source_type for node in evidence_graph.nodes}
        evidence_categories = {
            str(node.metadata.get("evidence_category", ""))
            for node in evidence_graph.nodes
        }
        if "evidence_image" in source_types or evidence_categories.intersection(
            {"image", "video", "image_observation", "video_analysis_report"}
        ):
            _upsert_affinity(
                affinities,
                "image_video_evidence",
                0.75,
                "material_type",
                "证据材料类型包含图像或报告",
            )
        if "identification" in evidence_categories:
            _upsert_affinity(
                affinities,
                "identification",
                0.75,
                "material_type",
                "证据材料类型为辨认材料",
            )
        if any(edge.edge_type == "contradicts" for edge in evidence_graph.edges):
            _upsert_affinity(affinities, "evidence_review", 0.70, "graph", "证据图存在冲突边")
            _upsert_affinity(affinities, "supplementary_investigation", 0.60, "graph", "冲突事实需要补证")
        return sorted(affinities.values(), key=lambda item: item.score, reverse=True)


def _upsert_affinity(
    affinities: dict[str, DomainAffinity],
    domain_id: str,
    score: float,
    source: str,
    reason: str,
) -> None:
    current = affinities.get(domain_id)
    if current is None or score > current.score:
        affinities[domain_id] = DomainAffinity(domain_id, score, source, reason)


def attach_chunk_affinities(chunk: LegalChunk) -> LegalChunk:
    return replace(chunk, domain_affinities=DomainAffinityIndexer().score_chunk(chunk))
