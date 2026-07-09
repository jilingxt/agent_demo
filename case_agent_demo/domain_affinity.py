from __future__ import annotations

from dataclasses import replace

from case_agent_demo.models import DomainAffinity, EvidenceGraph, LegalChunk, LegalDocument, LegalDomain


DEFAULT_LEGAL_DOMAINS = [
    LegalDomain("criminal_injury", "故意伤害领域", keywords=["故意伤害", "殴打", "轻伤", "重伤", "伤情", "他人身体"]),
    LegalDomain("property_damage", "故意毁坏财物领域", keywords=["故意毁坏", "毁坏", "损坏", "财物", "价格认定"]),
    LegalDomain("theft", "盗窃领域", keywords=["盗窃", "窃取", "非法占有", "扒窃", "拿走"]),
    LegalDomain("public_security_punishment", "治安处罚领域", keywords=["治安管理", "处罚", "拘留", "罚款"]),
    LegalDomain("procedure_compliance", "办案程序规范领域", keywords=["程序", "告知", "询问", "扣押", "调取", "送达", "办案"]),
    LegalDomain("evidence_review", "证据审查领域", keywords=["证据", "证明", "真实性", "关联性", "合法性", "审查"]),
    LegalDomain("forensic_injury", "伤情鉴定领域", keywords=["鉴定", "伤情", "轻伤二级", "人体损伤", "鉴定意见"]),
    LegalDomain("image_video_evidence", "图片/监控/视听资料领域", keywords=["图片", "监控", "视频", "视听资料", "照片"]),
    LegalDomain("identification", "辨认领域", keywords=["辨认", "辨认笔录", "照片辨认"]),
    LegalDomain("statement_review", "询问笔录/证人证言审查领域", keywords=["询问", "笔录", "证人证言", "讯问"]),
    LegalDomain("supplementary_investigation", "补充侦查/补证领域", keywords=["补充侦查", "补证", "补充调取", "补充询问"]),
    LegalDomain("report_boundary", "报告边界/禁止最终判断领域", keywords=["辅助分析", "不得", "最终结论", "边界"]),
]


class DomainAffinityIndexer:
    def __init__(self, domains: list[LegalDomain] | None = None) -> None:
        self.domains = domains or DEFAULT_LEGAL_DOMAINS

    def score_text(self, text: str, manual_affinities: dict[str, float] | None = None) -> list[DomainAffinity]:
        affinities: list[DomainAffinity] = []
        for domain in self.domains:
            hits = sum(1 for keyword in domain.keywords if keyword in text)
            manual = (manual_affinities or {}).get(domain.domain_id)
            keyword_score = min(1.0, hits / max(1, min(3, len(domain.keywords))))
            if manual is not None:
                score = 0.60 * manual + 0.40 * keyword_score
            else:
                score = keyword_score
            if score > 0:
                affinities.append(DomainAffinity(domain.domain_id, round(score, 4), "keyword", f"命中 {hits} 个领域关键词"))
        return sorted(affinities, key=lambda item: item.score, reverse=True)

    def score_document(self, document: LegalDocument, chunks: list[LegalChunk]) -> list[DomainAffinity]:
        text = " ".join([document.title, *[chunk.text for chunk in chunks]])
        return self.score_text(text)

    def score_chunk(self, chunk: LegalChunk) -> list[DomainAffinity]:
        return self.score_text(f"{chunk.title} {chunk.article} {chunk.text}")


class CaseDomainRouter:
    def infer_domains(self, case_type: str, evidence_graph: EvidenceGraph) -> list[DomainAffinity]:
        text = f"{case_type} " + " ".join(f"{fact.behavior} {fact.object}" for fact in evidence_graph.facts)
        affinities = {item.domain_id: item for item in DomainAffinityIndexer().score_text(text)}
        if "故意伤害" in case_type:
            affinities["criminal_injury"] = DomainAffinity("criminal_injury", 0.90, "case_type", "案件类型命中故意伤害")
            affinities["forensic_injury"] = DomainAffinity("forensic_injury", max(0.75, affinities.get("forensic_injury", DomainAffinity("", 0)).score), "case_type", "故意伤害常需伤情鉴定")
            affinities["evidence_review"] = DomainAffinity("evidence_review", max(0.65, affinities.get("evidence_review", DomainAffinity("", 0)).score), "case_type", "证据审查基础领域")
        if any(word in text for word in ("轻伤", "重伤", "骨折", "鉴定")):
            affinities["forensic_injury"] = DomainAffinity("forensic_injury", max(0.85, affinities.get("forensic_injury", DomainAffinity("", 0)).score), "graph", "事实包含伤情或鉴定")
        if any(word in text for word in ("监控", "图片", "照片", "视频")):
            affinities["image_video_evidence"] = DomainAffinity("image_video_evidence", 0.75, "graph", "事实包含图像视频材料")
        if any(edge.edge_type == "contradicts" for edge in evidence_graph.edges):
            affinities["evidence_review"] = DomainAffinity("evidence_review", 0.70, "graph", "证据图存在冲突边")
            affinities["supplementary_investigation"] = DomainAffinity("supplementary_investigation", 0.60, "graph", "冲突事实需要补证")
        if "辨认" in text:
            affinities["identification"] = DomainAffinity("identification", 0.75, "graph", "事实包含辨认材料")
        return sorted(affinities.values(), key=lambda item: item.score, reverse=True)


def attach_chunk_affinities(chunk: LegalChunk) -> LegalChunk:
    return replace(chunk, domain_affinities=DomainAffinityIndexer().score_chunk(chunk))
