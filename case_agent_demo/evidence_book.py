"""Deterministic, case-neutral evidence dossier construction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from case_agent_demo.models import (
    AllegationRecord,
    ClaimAssessment,
    EvidenceAssertion,
    EvidenceBook,
    EvidenceFinding,
    EvidenceGraph,
    IdentificationRecord,
    LegalCandidate,
    LegalMatch,
    ObjectiveCircumstance,
    ParticipantRecord,
)


_BOUNDARY = (
    "本证据册只说明当前材料对各项事实命题的支持、反对和不确定状态，"
    "不代替执法、检察或审判机关作出违法、犯罪、责任或者处罚的最终认定。"
)


@dataclass
class EvidenceBookBuilder:
    def build(
        self,
        graph: EvidenceGraph,
        assertions: list[EvidenceAssertion],
        assessments: list[ClaimAssessment],
        *,
        legal_matches: list[LegalMatch] | None = None,
        legal_purpose: str = "candidate_discovery",
        bayesian_result: dict | None = None,
    ) -> EvidenceBook:
        nodes = {node.node_id: node for node in graph.nodes}
        assessments_by_id = {item.claim_id: item for item in assessments}
        participants = _participants(assertions)
        allegations = _allegations(assertions, nodes)
        findings = [
            _finding(claim, assessments_by_id.get(claim.claim_id), nodes, assertions)
            for claim in graph.claims
        ]
        objective = _objective_circumstances(assertions, nodes)
        identifications = _identifications(assertions, nodes)
        conflicts = [
            edge.edge_id
            for edge in graph.edges
            if edge.status == "active" and edge.edge_type == "contradicts"
        ]
        candidates = [
            LegalCandidate(
                law_id=item.law_id,
                law_name=item.law_name,
                article=item.article,
                retrieval_purpose=_legal_purpose(item, legal_purpose),
                candidate_basis=item.matched_behavior,
                matched_elements=[item.legal_element] if item.legal_element else [],
            )
            for item in legal_matches or []
        ]
        bayesian_result = bayesian_result or {}
        missing = _missing_evidence(findings)
        return EvidenceBook(
            participants=participants,
            allegations=allegations,
            fact_findings=findings,
            objective_circumstances=objective,
            identifications=identifications,
            conflicts=conflicts,
            legal_candidates=candidates,
            bayesian_runs=list(bayesian_result.get("runs", [])),
            bayesian_abstentions=list(bayesian_result.get("abstentions", [])),
            missing_evidence=missing,
            conclusion_boundary=_BOUNDARY,
        )


def _participants(assertions: list[EvidenceAssertion]) -> list[ParticipantRecord]:
    roles: dict[str, set[str]] = defaultdict(set)
    assertion_ids: dict[str, set[str]] = defaultdict(set)
    for assertion in assertions:
        include_declarant = not (
            assertion.assertion_role == "evidence_observation"
            and not assertion.declarant_role
        )
        if (
            include_declarant
            and assertion.declarant
            and assertion.declarant not in {"unknown", "未识别人员"}
        ):
            declarant_role = assertion.declarant_role or _declarant_role(assertion)
            roles[assertion.declarant].add(declarant_role)
            assertion_ids[assertion.declarant].add(assertion.assertion_id)
        if assertion.actor and assertion.actor not in {"unknown", "未识别人员"}:
            actor_role = str(assertion.metadata.get("actor_role", "")) or (
                "alleged_actor" if assertion.assertion_role == "allegation" else "involved_person"
            )
            roles[assertion.actor].add(actor_role)
            assertion_ids[assertion.actor].add(assertion.assertion_id)
        if assertion.target_person and assertion.target_person not in {"unknown", "未识别人员"}:
            target_role = str(assertion.metadata.get("target_role", "")) or "affected_person"
            roles[assertion.target_person].add(target_role)
            assertion_ids[assertion.target_person].add(assertion.assertion_id)
    return [
        ParticipantRecord(
            name=name,
            roles=sorted(value),
            assertion_ids=sorted(assertion_ids[name]),
        )
        for name, value in sorted(roles.items())
    ]


def _declarant_role(assertion: EvidenceAssertion) -> str:
    if assertion.assertion_role == "allegation":
        return "reporting_person"
    if assertion.assertion_role == "defense_response":
        return "alleged_actor"
    if assertion.assertion_role == "evidence_observation":
        return "record_source"
    return "statement_provider"


def _allegations(assertions, nodes) -> list[AllegationRecord]:
    result = []
    for assertion in assertions:
        if assertion.assertion_role != "allegation" or assertion.stance != "affirm":
            continue
        node = nodes.get(assertion.node_id)
        result.append(
            AllegationRecord(
                allegation_id=f"ALG-{assertion.assertion_id}",
                reporter=assertion.declarant,
                alleged_actor=assertion.actor,
                predicate=assertion.predicate,
                factual_summary=(node.summary if node is not None else assertion.predicate),
                target_person=assertion.target_person,
                object=assertion.object,
                time=assertion.time or (node.time if node is not None else ""),
                location=assertion.location or (node.location if node is not None else ""),
                assertion_ids=[assertion.assertion_id],
            )
        )
    return result


def _finding(claim, assessment, nodes, assertions) -> EvidenceFinding:
    related_nodes = [
        nodes[node_id]
        for node_id in (
            claim.supporting_node_ids + claim.opposing_node_ids + claim.ambiguous_node_ids
        )
        if node_id in nodes
    ]
    time = claim.time_bucket or next((node.time for node in related_nodes if node.time), "")
    location = claim.location or next(
        (node.location for node in related_nodes if node.location), ""
    )
    status = assessment.status if assessment is not None else "unassessed"
    objective_negative = any(
        assertion.node_id in claim.opposing_node_ids
        and assertion.assertion_role == "evidence_observation"
        and assertion.stance == "deny"
        for assertion in assertions
    )
    if (
        objective_negative
        and assessment is not None
        and assessment.opinion is not None
        and assessment.opinion.opposition >= assessment.opinion.support
    ):
        status = "objectively_opposed"
    return EvidenceFinding(
        claim_id=claim.claim_id,
        subject=claim.subject,
        predicate=claim.behavior_type,
        status=status,
        target_person=claim.target_person,
        object=claim.object,
        time=time,
        location=location,
        supporting_node_ids=list(dict.fromkeys(claim.supporting_node_ids)),
        opposing_node_ids=list(dict.fromkeys(claim.opposing_node_ids)),
        ambiguous_node_ids=list(dict.fromkeys(claim.ambiguous_node_ids)),
        support_index=float(assessment.support_index) if assessment is not None else 0.0,
        reasons=list(assessment.reasons) if assessment is not None else [],
        conclusion=_finding_conclusion(status),
    )


def _objective_circumstances(assertions, nodes) -> list[ObjectiveCircumstance]:
    result = []
    seen = set()
    for assertion in assertions:
        if assertion.assertion_role != "evidence_observation" or assertion.node_id in seen:
            continue
        node = nodes.get(assertion.node_id)
        if node is None:
            continue
        seen.add(assertion.node_id)
        result.append(
            ObjectiveCircumstance(
                node_id=node.node_id,
                source_material_id=node.source_material_id,
                category=assertion.evidence_category or node.source_type,
                summary=node.summary,
                time=assertion.time or node.time,
                location=assertion.location or node.location,
            )
        )
    return result


def _identifications(assertions, nodes) -> list[IdentificationRecord]:
    result = []
    seen = set()
    for assertion in assertions:
        if (
            assertion.evidence_category != "identification"
            or assertion.node_id in seen
        ):
            continue
        node = nodes.get(assertion.node_id)
        if node is None:
            continue
        seen.add(assertion.node_id)
        result.append(
            IdentificationRecord(
                node_id=node.node_id,
                source_material_id=node.source_material_id,
                identifier=assertion.declarant or assertion.actor,
                identified_person=assertion.target_person or assertion.object,
                summary=node.summary,
                time=assertion.time or node.time,
                location=assertion.location or node.location,
            )
        )
    return result


def _finding_conclusion(status: str) -> str:
    return {
        "authority_anchored": "当前有经核验的权威材料支持该事实命题。",
        "supported": "当前证据支持该事实命题。",
        "contested": "正反材料均存在，当前尚不能确认或否定该事实命题。",
        "contested_but_not_refuted": "正向证据仍占优势，但存在反向材料，需要继续补强。",
        "objectively_opposed": "现有客观材料不支持该事实命题，当前不足以确认该行为发生。",
        "opposing_dominant": "反向证据占优，当前不足以确认该事实命题。",
        "insufficient": "现有证据不足以形成稳定判断。",
        "unassessed": "该事实命题尚未完成证据评估。",
    }.get(status, "该事实命题需要人工复核。")


def _missing_evidence(findings: list[EvidenceFinding]) -> list[str]:
    result = []
    for finding in findings:
        if finding.status not in {"contested", "insufficient", "opposing_dominant", "unassessed"}:
            continue
        subject = finding.subject or "相关人员"
        target = finding.target_person or finding.object
        result.append(
            f"围绕 {subject} / {finding.predicate} / {target or '相关对象'} 补充独立来源材料，"
            "并核对时间、地点、行为对象及原始载体。"
        )
    return list(dict.fromkeys(result))


def _legal_purpose(item: LegalMatch, fallback: str) -> str:
    parts = item.source.split(":")
    if len(parts) >= 2 and parts[0] in {"legal_kb", "legal_retrieval_tool"}:
        return parts[1]
    return fallback
