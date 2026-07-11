from __future__ import annotations

import json
import math
import re
from dataclasses import replace
from pathlib import Path

from case_agent_demo.models import (
    AuthorityAssessment,
    ClaimAssessment,
    ClaimOpinion,
    EvidenceAssertion,
    EvidenceClaim,
    EvidenceGraph,
    infer_claim_type,
)


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

_AUTHORITY_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "authority_rules.json"
_VERIFICATION_FIELDS = (
    "competence_verified",
    "authenticity_verified",
    "procedure_verified",
    "subject_identity_verified",
    "method_verified",
    "standard_verified",
    "scope_verified",
)
_FALLBACK_AUTHORITY_RULES = (
    {
        "id": "verified_forensic_injury_grade_v1",
        "issuers": ["qualified_forensic_institution"],
        "document_types": ["forensic_injury_grade_report", "forensic_injury_reappraisal"],
        "predicates": ["injury_exists", "injury_grade"],
        "mean": 0.99,
        "strength": 50.0,
        "requires_human_verification": True,
    },
)


class AuthorityValidator:
    def __init__(self, rules_path: str | Path | None = None):
        path = Path(rules_path) if rules_path is not None else _AUTHORITY_RULES_PATH
        try:
            self.rules = json.loads(path.read_text(encoding="utf-8")).get("rules", [])
        except OSError:
            self.rules = list(_FALLBACK_AUTHORITY_RULES)

    def validate(self, assertion: EvidenceAssertion) -> AuthorityAssessment:
        metadata = assertion.metadata.get("authority")
        if not isinstance(metadata, dict):
            return AuthorityAssessment(reasons=["no explicit authority metadata"])

        issuer = _text_value(metadata.get("issuer"))
        document_type = _text_value(metadata.get("document_type"))
        verification = {field: metadata.get(field) is True for field in _VERIFICATION_FIELDS}
        defeater = metadata.get("defeater") is True
        rule = self._matching_rule(issuer, document_type)
        if rule is None:
            return AuthorityAssessment(
                issuer=issuer,
                document_type=document_type,
                defeater=defeater,
                reasons=["issuer and document type do not match an authority rule"],
                **verification,
            )

        missing = [field for field in _VERIFICATION_FIELDS if not verification[field]]
        if rule.get("requires_human_verification") and metadata.get("human_verified") is not True:
            missing.append("human_verified")
        if missing:
            return AuthorityAssessment(
                issuer=issuer,
                document_type=document_type,
                defeater=defeater,
                reasons=[f"missing explicit verification: {', '.join(missing)}"],
                **verification,
            )
        if assertion.predicate not in rule.get("predicates", []):
            return AuthorityAssessment(
                issuer=issuer,
                document_type=document_type,
                defeater=defeater,
                status="out_of_scope",
                reasons=["assertion predicate is outside the configured authority scope"],
                **verification,
            )

        return AuthorityAssessment(
            issuer=issuer,
            document_type=document_type,
            defeater=defeater,
            status="authority_contested" if defeater else "authority_valid",
            mean=float(rule["mean"]),
            strength=float(rule["strength"]),
            reasons=["explicit verification satisfies the configured authority rule"],
            **verification,
        )

    def _matching_rule(self, issuer: str, document_type: str) -> dict | None:
        for rule in self.rules:
            if issuer in rule.get("issuers", []) and document_type in rule.get("document_types", []):
                return rule
        return None


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

    def __init__(
        self,
        quality_evaluator: EvidenceQualityEvaluator | None = None,
        authority_validator: AuthorityValidator | None = None,
    ):
        self.quality_evaluator = quality_evaluator or EvidenceQualityEvaluator()
        self.authority_validator = authority_validator or AuthorityValidator()

    def evaluate(self, claim: EvidenceClaim, assertions: list[EvidenceAssertion]) -> ClaimAssessment:
        authority_assessments = [(assertion, self.authority_validator.validate(assertion)) for assertion in assertions]
        authority_assertion_ids = {
            assertion.assertion_id
            for assertion, authority in authority_assessments
            if authority.status in {"authority_valid", "authority_contested"}
        }
        ordinary_assertions = [
            assertion
            for assertion in assertions
            if assertion.assertion_id not in authority_assertion_ids and _assertion_matches_claim(assertion, claim)
        ]
        support = self._strongest_strengths(claim, ordinary_assertions, "affirm")
        opposition = self._strongest_strengths(claim, ordinary_assertions, "deny")
        authority_support, authority_opposition, applicable_authorities = self._authority_evidence(
            claim, authority_assessments
        )
        positive_evidence = sum(support) + authority_support
        negative_evidence = sum(opposition) + authority_opposition
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
        ambiguous_count = sum(1 for assertion in ordinary_assertions if _normalize_stance(assertion.stance) == "ambiguous")
        provenance_group_count = self.independent_group_count(claim, assertions)
        status = _authority_aware_status(opinion, applicable_authorities)
        reasons = _assessment_reasons(
            len(support) + sum(1 for stance, _ in applicable_authorities if stance == "affirm"),
            len(opposition) + sum(1 for stance, _ in applicable_authorities if stance == "deny"),
            provenance_group_count,
            ambiguous_count,
            opinion,
        )
        reasons.extend(_authority_reasons(applicable_authorities))
        return ClaimAssessment(
            claim_id=claim.claim_id,
            opinion=opinion,
            status=status,
            reasons=reasons,
            authority_assessments=[authority for _, authority in authority_assessments],
        )

    def _authority_evidence(
        self,
        claim: EvidenceClaim,
        authority_assessments: list[tuple[EvidenceAssertion, AuthorityAssessment]],
    ) -> tuple[float, float, list[tuple[str, AuthorityAssessment]]]:
        evidence_by_origin: dict[str, tuple[str, AuthorityAssessment]] = {}
        for assertion, authority in authority_assessments:
            stance = _normalize_stance(assertion.stance)
            if (
                authority.status not in {"authority_valid", "authority_contested"}
                or assertion.predicate != claim.behavior_type
                or not _assertion_matches_claim(assertion, claim)
                or stance not in {"affirm", "deny"}
            ):
                continue
            origin = assertion.origin_evidence or assertion.source_group or assertion.assertion_id
            existing = evidence_by_origin.get(origin)
            if existing is None or authority.strength > existing[1].strength:
                evidence_by_origin[origin] = (stance, authority)

        applicable = list(evidence_by_origin.values())
        support = 0.0
        opposition = 0.0
        for stance, authority in applicable:
            positive_amount = authority.mean * authority.strength
            negative_amount = (1.0 - authority.mean) * authority.strength
            if stance == "affirm":
                support += positive_amount
                opposition += negative_amount
            else:
                support += negative_amount
                opposition += positive_amount
        return support, opposition, applicable

    def independent_group_count(self, claim: EvidenceClaim, assertions: list[EvidenceAssertion]) -> int:
        del claim
        return _provenance_group_count(
            [assertion for assertion in assertions if _normalize_stance(assertion.stance) in {"affirm", "deny"}]
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
            "source_material_id": node.source_material_id,
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

    def build_claims(self, assertions: list[EvidenceAssertion], graph: EvidenceGraph | None = None) -> list[EvidenceClaim]:
        claims = self.normalizer.build_claims(assertions)
        if graph is None:
            return claims
        edge_ids_by_node = _active_edge_ids_by_node(graph)
        return [
            replace(
                claim,
                related_edge_ids=sorted(
                    {
                        edge_id
                        for node_id in claim.supporting_node_ids + claim.opposing_node_ids + claim.ambiguous_node_ids
                        for edge_id in edge_ids_by_node.get(node_id, [])
                    }
                ),
            )
            for claim in claims
        ]


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


def _authority_aware_status(
    opinion: ClaimOpinion,
    authorities: list[tuple[str, AuthorityAssessment]],
) -> str:
    if any(authority.status == "authority_contested" for _, authority in authorities):
        return "authority_contested"
    if authorities:
        return "authority_anchored"
    return _assessment_status(opinion)


def _authority_reasons(authorities: list[tuple[str, AuthorityAssessment]]) -> list[str]:
    reasons = []
    for stance, authority in authorities:
        description = f"{authority.issuer} {authority.document_type}".strip()
        if authority.status == "authority_contested":
            reasons.append(f"authoritative defeater from {description} contests this claim")
        else:
            reasons.append(f"authority anchor from {description} contributes {stance} evidence")
    return reasons


def _text_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _assertion_matches_claim(assertion: EvidenceAssertion, claim: EvidenceClaim) -> bool:
    # Unscoped legacy assertions are passed directly by older callers as claim-local evidence.
    if _is_unscoped_legacy_assertion(assertion):
        return True
    return (
        assertion.actor == claim.subject
        and assertion.predicate == claim.behavior_type
        and _normalized_target(assertion.target_person, assertion.object)
        == _normalized_target(claim.target_person, claim.object)
        and (not claim.event_id or assertion.event_id == claim.event_id)
    )


def _is_unscoped_legacy_assertion(assertion: EvidenceAssertion) -> bool:
    return (
        not assertion.actor
        and assertion.predicate in {"", "general"}
        and not _normalized_target(assertion.target_person, assertion.object)
        and not assertion.event_id
    )


def _normalized_target(target_person: str, obj: str) -> str:
    return (target_person or obj).strip().casefold()


def _assessment_reasons(
    support_groups: int,
    opposition_groups: int,
    provenance_group_count: int,
    ambiguous_count: int,
    opinion: ClaimOpinion,
) -> list[str]:
    reasons = []
    if support_groups:
        reasons.append(f"{support_groups} independent supporting source group(s)")
    if opposition_groups:
        reasons.append(f"{opposition_groups} independent denying source group(s)")
    if provenance_group_count:
        reasons.append(f"{provenance_group_count} independent provenance group(s) overall")
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


def _active_edge_ids_by_node(graph: EvidenceGraph) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in graph.edges:
        if edge.status != "active":
            continue
        for node_id in (edge.source_node_id, edge.target_node_id):
            result.setdefault(node_id, []).append(edge.edge_id)
    return result


def _provenance_group_count(assertions: list[EvidenceAssertion]) -> int:
    parents: dict[str, str] = {}

    def find(key: str) -> str:
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = find(parents[key])
        return parents[key]

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for assertion in assertions:
        keys = []
        if assertion.origin_evidence:
            keys.append(f"origin:{assertion.origin_evidence}")
        if assertion.source_group:
            keys.append(f"source:{assertion.source_group}")
        if not keys:
            keys.append(f"assertion:{assertion.assertion_id}")
        for key in keys[1:]:
            union(keys[0], key)
        find(keys[0])
    return len({find(key) for key in parents})
