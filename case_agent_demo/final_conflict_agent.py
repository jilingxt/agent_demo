from __future__ import annotations

from dataclasses import dataclass, field

from case_agent_demo.models import Challenge, EvidenceGraph, LegalRAGResult


@dataclass(frozen=True)
class ValidationIssue:
    issue_id: str
    issue_type: str
    severity: str
    target_node_ids: list[str] = field(default_factory=list)
    target_edge_ids: list[str] = field(default_factory=list)
    target_claim_ids: list[str] = field(default_factory=list)
    reason: str = ""
    required_action: str = ""
    supporting_law_ids: list[str] = field(default_factory=list)
    supporting_chunk_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


SUPPLEMENTARY_INVESTIGATION_ACTIONS = {
    "violence": ["补充调取现场监控或周边监控", "询问现场在场人员或独立证人", "核对伤情形成时间与行为因果关系"],
    "property_damage": ["补充固定损坏物品照片、维修记录或价格认定材料", "核对物品权属和损坏前后状态"],
    "taking_property": ["补充调取监控或电子轨迹", "核对物品权属、去向和占有状态"],
    "presence": ["核对监控、门禁、定位或考勤记录", "询问同场人员"],
    "injury_consequence": ["核对鉴定意见所依据的病历、影像资料和检查记录", "审查伤情形成机制与陈述行为是否一致"],
    "general": ["补充核对原始材料来源", "补充询问相关人员"],
}


class FinalConflictAgent:
    def review(
        self,
        confirmed_case_type: str,
        evidence_graph: EvidenceGraph,
        draft_report: str,
        legal_rag_result: LegalRAGResult,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        counter = 1
        for edge in evidence_graph.edges:
            if edge.edge_type == "contradicts":
                issues.append(
                    ValidationIssue(
                        issue_id=f"V-{counter}",
                        issue_type="evidence_conflict",
                        severity="high" if edge.confidence >= 0.85 else "medium",
                        target_edge_ids=[edge.edge_id],
                        reason=edge.reason or "证据图存在冲突关系。",
                        required_action="；".join(SUPPLEMENTARY_INVESTIGATION_ACTIONS["general"]),
                    )
                )
                counter += 1
        for claim in evidence_graph.claims:
            profile = claim.confidence_profile
            if profile is None:
                continue
            if profile.label == "争议事实，尚不足以否定":
                issues.append(_claim_issue(counter, "contested_but_not_refuted", "medium", claim.claim_id, claim.behavior_type, profile.label))
                counter += 1
            elif profile.label in {"明显存疑，需补强", "低可信或被冲突削弱"}:
                issues.append(_claim_issue(counter, "evidence_insufficiency", "high", claim.claim_id, claim.behavior_type, profile.label))
                counter += 1
        if not legal_rag_result.matches or not legal_rag_result.chunks:
            issues.append(
                ValidationIssue(
                    issue_id=f"V-{counter}",
                    issue_type="legal_basis_missing",
                    severity="high",
                    reason="缺少可追溯法律或规范依据。",
                    required_action="补充检索法律、程序规范、证据审查和鉴定相关依据。",
                )
            )
            counter += 1
        if any(phrase in draft_report for phrase in ("已经构成犯罪", "应当处罚", "必然构成", "依法应当追究")):
            issues.append(
                ValidationIssue(
                    issue_id=f"V-{counter}",
                    issue_type="report_overclaim",
                    severity="high",
                    reason="报告包含最终裁判式结论。",
                    required_action="改写为辅助分析表述，并标注需人工复核。",
                )
            )
            counter += 1
        for node in evidence_graph.nodes:
            if node.source_type in {"evidence_image", "report_image"} and node.confidence < 0.75:
                issues.append(
                    ValidationIssue(
                        issue_id=f"V-{counter}",
                        issue_type="image_evidence_low_confidence",
                        severity="medium",
                        target_node_ids=[node.node_id],
                        reason="图片或报告图片识别置信度较低。",
                        required_action="人工核对图片原件、OCR文字和来源信息。",
                    )
                )
                counter += 1
        return issues


def issues_to_challenges(issues: list[ValidationIssue]) -> list[Challenge]:
    return [
        Challenge(
            challenge_id=issue.issue_id,
            challenge_type=issue.issue_type,
            target=",".join(issue.target_claim_ids or issue.target_node_ids or issue.target_edge_ids),
            reason=f"{issue.reason} 建议：{issue.required_action}",
            severity=issue.severity,
        )
        for issue in issues
    ]


def _claim_issue(counter: int, issue_type: str, severity: str, claim_id: str, behavior_type: str, label: str) -> ValidationIssue:
    actions = SUPPLEMENTARY_INVESTIGATION_ACTIONS.get(behavior_type) or SUPPLEMENTARY_INVESTIGATION_ACTIONS["general"]
    return ValidationIssue(
        issue_id=f"V-{counter}",
        issue_type=issue_type,
        severity=severity,
        target_claim_ids=[claim_id],
        reason=f"事实命题置信度标签为“{label}”。",
        required_action="；".join(actions),
    )
