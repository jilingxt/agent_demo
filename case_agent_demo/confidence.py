from __future__ import annotations

import re
from dataclasses import replace

from case_agent_demo.evidence_reasoning import AssertionNormalizer, ClaimBuilderV2, SubjectiveEvidenceEngine
from case_agent_demo.models import ConfidenceProfile, EvidenceClaim, EvidenceGraph, EvidenceNode


LEGACY_LABELS = {
    "unassessed": "低可信或被冲突削弱",
    "supported": "有一定印证",
    "authority_anchored": "有一定印证",
    "contested": "争议事实，尚不足以否定",
    "authority_contested": "争议事实，尚不足以否定",
    "opposing_dominant": "低可信或被冲突削弱",
    "insufficient": "明显存疑，需补强",
}


class ClaimBuilder:
    def build_claims(self, graph: EvidenceGraph) -> list[EvidenceClaim]:
        buckets: dict[tuple[str, str, str, str], EvidenceClaim] = {}
        for node in graph.nodes:
            if node.node_type != "fact" or node.status != "active":
                continue
            key = (node.person or node.source_material_id, node.claim_type or "general", node.object, node.location)
            claim = buckets.get(key) or EvidenceClaim(
                claim_id=f"CL-{_safe(key[1])}-{_safe(key[0])}-{_safe(key[2])}",
                subject=key[0],
                behavior_type=key[1],
                object=key[2],
                location=key[3],
            )
            if node.polarity == "deny":
                buckets[key] = replace(claim, opposing_node_ids=[*claim.opposing_node_ids, node.node_id])
            else:
                buckets[key] = replace(claim, supporting_node_ids=[*claim.supporting_node_ids, node.node_id])

        edge_ids_by_node = _edge_ids_by_node(graph)
        return [
            replace(
                claim,
                related_edge_ids=sorted(
                    {edge_id for node_id in claim.supporting_node_ids + claim.opposing_node_ids for edge_id in edge_ids_by_node.get(node_id, [])}
                ),
            )
            for claim in buckets.values()
        ]

    def update_claims_for_new_node(
        self,
        graph: EvidenceGraph,
        new_node: EvidenceNode,
        existing_claims: list[EvidenceClaim],
    ) -> list[EvidenceClaim]:
        return self.build_claims(graph)


class ConfidenceEngine:
    def __init__(self, normalizer: AssertionNormalizer | None = None, subjective_engine: SubjectiveEvidenceEngine | None = None):
        self.normalizer = normalizer or AssertionNormalizer()
        self.claim_builder = ClaimBuilderV2(self.normalizer)
        self.subjective_engine = subjective_engine or SubjectiveEvidenceEngine()

    def score_claim(self, claim: EvidenceClaim, graph: EvidenceGraph) -> ConfidenceProfile:
        assertions = self._assertions_for_claim(claim, graph)
        assessment = self.subjective_engine.evaluate(claim, assertions)
        opinion = assessment.opinion
        support_quality = [
            self.subjective_engine.quality_evaluator.evaluate(assertion, claim)
            for assertion in assertions
            if assertion.stance == "affirm"
        ]
        average_quality = sum(support_quality) / len(support_quality) if support_quality else 0.0
        return ConfidenceProfile(
            extraction_quality=average_quality,
            source_reliability=average_quality,
            corroboration_score=opinion.support,
            contradiction_score=opinion.opposition,
            independence_score=min(1.0, self.subjective_engine.independent_group_count(claim, assertions) / 3),
            uncertainty=opinion.uncertainty,
            final_score=round(opinion.support + 0.5 * opinion.uncertainty, 4),
            label=LEGACY_LABELS.get(assessment.status, "低可信或被冲突削弱"),
            reasons=assessment.reasons,
        )

    def score_claims(self, graph: EvidenceGraph) -> list[EvidenceClaim]:
        assertions = self.normalizer.normalize_graph(graph)
        claims = graph.claims or self.claim_builder.build_claims(assertions, graph)
        return [replace(claim, confidence_profile=self.score_claim(claim, graph)) for claim in claims]

    def _assertions_for_claim(self, claim: EvidenceClaim, graph: EvidenceGraph):
        assertion_ids = set(claim.assertion_ids)
        node_ids = set(claim.supporting_node_ids + claim.opposing_node_ids + claim.ambiguous_node_ids)
        return [
            assertion
            for assertion in self.normalizer.normalize_graph(graph)
            if assertion.assertion_id in assertion_ids or assertion.node_id in node_ids
        ]


def _safe(text: str) -> str:
    return re.sub(r"\W+", "", text or "unknown")[:24] or "unknown"


def _edge_ids_by_node(graph: EvidenceGraph) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in graph.edges:
        for node_id in (edge.source_node_id, edge.target_node_id):
            result.setdefault(node_id, []).append(edge.edge_id)
    return result
