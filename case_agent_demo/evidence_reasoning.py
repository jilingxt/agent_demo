from __future__ import annotations

import math
import re
from dataclasses import replace

from case_agent_demo.models import ClaimAssessment, ClaimOpinion, EvidenceAssertion, EvidenceClaim, EvidenceGraph, infer_claim_type


QUALITY_DIMENSION_WEIGHTS = {
    "extraction_quality": 0.18,
    "relevance": 0.16,
    "specificity": 0.10,
    "directness": 0.15,
    "authenticity": 0.12,
    "procedural_integrity": 0.10,
    "internal_consistency": 0.10,
    "verifiability": 0.09,
}

SOURCE_TYPE_QUALITY = {
    "statement": 0.65,
    "evidence_image": 0.70,
    "report_image": 0.80,
    "official_report": 0.85,
    "forensic_report": 0.90,
    "party_submitted_image": 0.60,
    "manual_verified": 0.95,
}


class EvidenceQualityEvaluator:
    def evaluate(self, assertion: EvidenceAssertion, claim: EvidenceClaim) -> float:
        del claim
        metadata = assertion.metadata
        source_type_quality = SOURCE_TYPE_QUALITY.get(metadata.get("source_type"), 0.75)
        values = {
            "extraction_quality": _quality_value(metadata.get("extraction_quality", metadata.get("confidence", 0.75))),
            "relevance": _quality_value(metadata.get("relevance", 0.75)),
            "specificity": _quality_value(metadata.get("specificity", 0.75)),
            "directness": _quality_value(metadata.get("directness", 0.75)),
            "authenticity": _quality_value(metadata.get("authenticity", source_type_quality)),
            "procedural_integrity": _quality_value(metadata.get("procedural_integrity", source_type_quality)),
            "internal_consistency": _quality_value(metadata.get("internal_consistency", 0.75)),
            "verifiability": _quality_value(metadata.get("verifiability", source_type_quality)),
        }
        return math.prod(values[name] ** weight for name, weight in QUALITY_DIMENSION_WEIGHTS.items())


class SubjectiveEvidenceEngine:
    _BASE_RATE_EVIDENCE = 2.0

    def __init__(self, quality_evaluator: EvidenceQualityEvaluator | None = None):
        self.quality_evaluator = quality_evaluator or EvidenceQualityEvaluator()

    def evaluate(self, claim: EvidenceClaim, assertions: list[EvidenceAssertion]) -> ClaimAssessment:
        support = self._strongest_strengths(claim, assertions, "affirm")
        opposition = self._strongest_strengths(claim, assertions, "deny")
        positive_evidence = sum(support)
        negative_evidence = sum(opposition)
        total = positive_evidence + negative_evidence + self._BASE_RATE_EVIDENCE
        opinion = ClaimOpinion(
            claim_id=claim.claim_id,
            support=positive_evidence / total,
            opposition=negative_evidence / total,
            uncertainty=self._BASE_RATE_EVIDENCE / total,
            conflict=(2 * min(positive_evidence, negative_evidence) / (positive_evidence + negative_evidence))
            if positive_evidence + negative_evidence
            else 0.0,
        )
        ambiguous_count = sum(1 for assertion in assertions if _normalize_stance(assertion.stance) == "ambiguous")
        return ClaimAssessment(
            claim_id=claim.claim_id,
            opinion=opinion,
            status=_assessment_status(opinion),
            reasons=_assessment_reasons(len(support), len(opposition), ambiguous_count, opinion),
        )

    def independent_group_count(self, claim: EvidenceClaim, assertions: list[EvidenceAssertion]) -> int:
        return len(self._strongest_strengths(claim, assertions, "affirm")) + len(
            self._strongest_strengths(claim, assertions, "deny")
        )

    def _strongest_strengths(
        self,
        claim: EvidenceClaim,
        assertions: list[EvidenceAssertion],
        stance: str,
    ) -> list[float]:
        strongest_by_origin: dict[str, tuple[EvidenceAssertion, float]] = {}
        for assertion in assertions:
            if _normalize_stance(assertion.stance) != stance:
                continue
            strength = self.quality_evaluator.evaluate(assertion, claim)
            origin = assertion.origin_evidence or assertion.source_group or assertion.assertion_id
            previous = strongest_by_origin.get(origin)
            if previous is None or strength > previous[1]:
                strongest_by_origin[origin] = (assertion, strength)

        strongest_by_source_group: dict[str, float] = {}
        for assertion, strength in strongest_by_origin.values():
            source_group = assertion.source_group or assertion.origin_evidence or assertion.assertion_id
            strongest_by_source_group[source_group] = max(strength, strongest_by_source_group.get(source_group, 0.0))
        return list(strongest_by_source_group.values())


class AssertionNormalizer:
    def normalize_graph(self, graph: EvidenceGraph) -> list[EvidenceAssertion]:
        return [self.normalize_node(node) for node in graph.nodes if node.node_type == "fact" and node.status == "active"]

    def normalize_node(self, node) -> EvidenceAssertion:
        metadata = {
            **node.metadata,
            "extraction_quality": node.metadata.get("extraction_quality", node.confidence),
            "source_type": node.source_type,
        }
        actor = metadata.get("actor", node.person)
        predicate = metadata.get("predicate") or node.claim_type or infer_claim_type(node.behavior or node.summary, node.object)
        stance = _normalize_stance(metadata.get("stance", node.polarity))
        target_person = metadata.get("target_person", metadata.get("target", ""))
        origin_evidence = metadata.get("origin_evidence", node.raw_ref or node.source_material_id)
        return EvidenceAssertion(
            assertion_id=f"AS-{node.node_id}",
            node_id=node.node_id,
            declarant=metadata.get("declarant", node.source_party),
            actor=actor,
            predicate=predicate,
            target_person=target_person,
            object=metadata.get("object", node.object),
            event_id=metadata.get("event_id", metadata.get("event", "")),
            stance=stance,
            modality=metadata.get("modality", ""),
            source_group=metadata.get("source_group", node.source_material_id),
            origin_evidence=origin_evidence,
            metadata=metadata,
        )

    def build_claims(self, assertions: list[EvidenceAssertion]) -> list[EvidenceClaim]:
        buckets: dict[tuple[str, str, str, str], EvidenceClaim] = {}
        for assertion in assertions:
            target = assertion.target_person or assertion.object
            key = (assertion.actor, assertion.predicate, target, assertion.event_id)
            claim = buckets.get(key) or EvidenceClaim(
                claim_id=_claim_id(key),
                subject=assertion.actor,
                behavior_type=assertion.predicate,
                object=assertion.object,
                target_person=assertion.target_person,
                event_id=assertion.event_id,
            )
            claim = replace(
                claim,
                target_person=claim.target_person or assertion.target_person,
                object=claim.object or assertion.object,
                assertion_ids=[*claim.assertion_ids, assertion.assertion_id],
            )
            if assertion.stance == "affirm":
                claim = replace(claim, supporting_node_ids=[*claim.supporting_node_ids, assertion.node_id])
            elif assertion.stance == "deny":
                claim = replace(claim, opposing_node_ids=[*claim.opposing_node_ids, assertion.node_id])
            else:
                claim = replace(claim, ambiguous_node_ids=[*claim.ambiguous_node_ids, assertion.node_id])
            buckets[key] = claim
        return list(buckets.values())


class ClaimBuilderV2:
    def __init__(self, normalizer: AssertionNormalizer | None = None):
        self.normalizer = normalizer or AssertionNormalizer()

    def build_claims(self, assertions: list[EvidenceAssertion]) -> list[EvidenceClaim]:
        return self.normalizer.build_claims(assertions)


def _normalize_stance(stance: str) -> str:
    if stance in {"affirm", "support"}:
        return "affirm"
    if stance in {"deny", "oppose"}:
        return "deny"
    return "ambiguous"


def _quality_value(value: object) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.75


def _assessment_status(opinion: ClaimOpinion) -> str:
    if opinion.uncertainty == 1.0:
        return "unassessed"
    if opinion.conflict >= 0.50:
        return "contested"
    if opinion.opposition > opinion.support:
        return "opposing_dominant"
    if opinion.support >= 0.50:
        return "supported"
    return "insufficient"


def _assessment_reasons(
    support_groups: int,
    opposition_groups: int,
    ambiguous_count: int,
    opinion: ClaimOpinion,
) -> list[str]:
    reasons = []
    if support_groups:
        reasons.append(f"{support_groups} independent supporting source group(s)")
    if opposition_groups:
        reasons.append(f"{opposition_groups} independent denying source group(s)")
    if ambiguous_count:
        reasons.append(f"{ambiguous_count} ambiguous assertion(s) did not affect support or opposition")
    if opinion.conflict >= 0.50:
        reasons.append("supporting and denying evidence conflict materially")
    if not reasons:
        reasons.append("no supporting or denying evidence")
    return reasons


def _claim_id(key: tuple[str, str, str, str]) -> str:
    return "CL-" + "-".join(_safe(part) for part in (key[1], key[0], key[2], key[3]))


def _safe(value: str) -> str:
    return re.sub(r"\W+", "", value or "unknown")[:24] or "unknown"
