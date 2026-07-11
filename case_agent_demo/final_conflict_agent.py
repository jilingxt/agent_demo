from __future__ import annotations

from dataclasses import dataclass, field

from case_agent_demo.models import Challenge, ClaimAssessment, EvidenceGraph, LegalRAGResult


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
    "violence": ["补充调取现场或周边监控", "询问独立在场人员", "核对行为与伤情的因果关系"],
    "property_damage": ["固定损坏物品照片、维修记录或价格认定材料", "核对权属和损坏前后状态"],
    "taking_property": ["补充调取监控或电子轨迹", "核对物品权属、去向和占有状态"],
    "presence": ["核对监控、门禁、定位或考勤记录", "询问同场人员"],
    "injury_exists": ["核对病历、影像资料和鉴定基础"],
    "injury_grade": ["核查鉴定主体、程序、对象对应和适用标准", "确认有无相反重新鉴定"],
    "injury_consequence": ["核对病历、影像资料和鉴定意见", "审查伤情形成机制"],
    "causation": ["核对伤情形成时间和损伤机制", "排除其他合理致伤原因", "补充独立客观材料"],
    "general": ["补充核对原始材料来源", "补充询问相关人员"],
}


class FinalConflictAgent:
    def review(
        self,
        confirmed_case_type: str,
        evidence_graph: EvidenceGraph,
        draft_report: str,
        legal_rag_result: LegalRAGResult,
        claim_assessments: list[ClaimAssessment] | None = None,
        bayesian_result: dict | None = None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        counter = 1

        for edge in evidence_graph.edges:
            if edge.edge_type != "contradicts":
                continue
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

        assessments = claim_assessments or []
        if assessments:
            claim_types = {claim.claim_id: claim.behavior_type for claim in evidence_graph.claims}
            for assessment in assessments:
                behavior_type = claim_types.get(assessment.claim_id, "general")
                if assessment.status in {"contested", "contested_but_not_refuted"}:
                    issues.append(
                        _claim_issue(
                            counter,
                            "contested_but_not_refuted",
                            "medium",
                            assessment.claim_id,
                            behavior_type,
                            "正向证据仍占优势或与反向证据相当，但存在实质争议。",
                        )
                    )
                    counter += 1
                elif assessment.status in {"insufficient", "unassessed"}:
                    issues.append(
                        _claim_issue(
                            counter,
                            "evidence_insufficiency",
                            "high",
                            assessment.claim_id,
                            behavior_type,
                            "现有证据不足以形成稳定判断。",
                        )
                    )
                    counter += 1
                elif assessment.status == "opposing_dominant":
                    issues.append(
                        _claim_issue(
                            counter,
                            "opposing_evidence_dominant",
                            "high",
                            assessment.claim_id,
                            behavior_type,
                            "反向证据当前占优，应避免将该命题作为既定事实。",
                        )
                    )
                    counter += 1
                elif assessment.status == "authority_contested":
                    issues.append(
                        _claim_issue(
                            counter,
                            "authority_contested",
                            "high",
                            assessment.claim_id,
                            behavior_type,
                            "权威意见存在同层级反证或有效性异议。",
                        )
                    )
                    counter += 1
        else:
            counter = self._append_legacy_claim_issues(issues, counter, evidence_graph)

        if (
            _is_intentional_injury_case(confirmed_case_type)
            and _has_authoritative_injury(assessments, evidence_graph)
            and _causation_is_insufficient(bayesian_result)
        ):
            issues.append(
                ValidationIssue(
                    issue_id=f"V-{counter}",
                    issue_type="causation_insufficient",
                    severity="high",
                    target_claim_ids=[
                        claim.claim_id
                        for claim in evidence_graph.claims
                        if claim.behavior_type == "causation"
                    ],
                    reason="损伤程度已有权威材料支持，但尚不足以确认由特定行为人及本案行为造成。",
                    required_action="；".join(SUPPLEMENTARY_INVESTIGATION_ACTIONS["causation"]),
                    metadata={"causation": (bayesian_result or {}).get("node_values", {}).get("causation")},
                )
            )
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
            if node.source_type not in {"evidence_image", "report_image"} or node.confidence >= 0.75:
                continue
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

    def _append_legacy_claim_issues(
        self,
        issues: list[ValidationIssue],
        counter: int,
        evidence_graph: EvidenceGraph,
    ) -> int:
        for claim in evidence_graph.claims:
            profile = claim.confidence_profile
            if profile is None:
                continue
            if profile.label == "争议事实，尚不足以否定":
                issues.append(
                    _claim_issue(
                        counter,
                        "contested_but_not_refuted",
                        "medium",
                        claim.claim_id,
                        claim.behavior_type,
                        profile.label,
                    )
                )
                counter += 1
            elif profile.label in {"明显存疑，需补强", "低可信或被冲突削弱"}:
                issues.append(
                    _claim_issue(
                        counter,
                        "evidence_insufficiency",
                        "high",
                        claim.claim_id,
                        claim.behavior_type,
                        profile.label,
                    )
                )
                counter += 1
        return counter


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


def _claim_issue(
    counter: int,
    issue_type: str,
    severity: str,
    claim_id: str,
    behavior_type: str,
    reason: str,
) -> ValidationIssue:
    actions = SUPPLEMENTARY_INVESTIGATION_ACTIONS.get(behavior_type)
    actions = actions or SUPPLEMENTARY_INVESTIGATION_ACTIONS["general"]
    return ValidationIssue(
        issue_id=f"V-{counter}",
        issue_type=issue_type,
        severity=severity,
        target_claim_ids=[claim_id],
        reason=reason,
        required_action="；".join(actions),
    )


def _has_authoritative_injury(
    assessments: list[ClaimAssessment],
    evidence_graph: EvidenceGraph,
) -> bool:
    claim_types = {claim.claim_id: claim.behavior_type for claim in evidence_graph.claims}
    return any(
        assessment.status == "authority_anchored"
        and claim_types.get(assessment.claim_id) in {"injury_exists", "injury_grade", "injury_consequence"}
        for assessment in assessments
    )


def _causation_is_insufficient(bayesian_result: dict | None) -> bool:
    if not bayesian_result:
        return True
    value = bayesian_result.get("node_values", {}).get("causation")
    return value is None or float(value) < 0.5

def _is_intentional_injury_case(case_type: str) -> bool:
    normalized = case_type.strip().lower().replace("-", "_")
    return (
        "故意伤害" in case_type
        or "intentional injury" in normalized
        or "intentional_injury" in normalized
    )
