from __future__ import annotations

import math
import re
from dataclasses import replace

from case_agent_demo.models import ConfidenceProfile, EvidenceClaim, EvidenceGraph, EvidenceNode


SOURCE_RELIABILITY = {
    "statement": 0.52,
    "evidence_image": 0.55,
    "report_image": 0.68,
    "official_report": 0.75,
    "forensic_report": 0.78,
    "party_submitted_image": 0.45,
    "manual_verified": 0.85,
}

PARTY_RELIABILITY = {
    "suspect": 0.45,
    "victim": 0.52,
    "witness": 0.58,
    "official": 0.75,
    "unknown": 0.50,
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
                opposing = [*claim.opposing_node_ids, node.node_id]
                buckets[key] = replace(claim, opposing_node_ids=opposing)
            else:
                supporting = [*claim.supporting_node_ids, node.node_id]
                buckets[key] = replace(claim, supporting_node_ids=supporting)

        edge_ids_by_node = _edge_ids_by_node(graph)
        claims = []
        for claim in buckets.values():
            node_ids = set(claim.supporting_node_ids + claim.opposing_node_ids)
            related_edge_ids = sorted({edge_id for node_id in node_ids for edge_id in edge_ids_by_node.get(node_id, [])})
            claims.append(replace(claim, related_edge_ids=related_edge_ids))
        return claims

    def update_claims_for_new_node(
        self,
        graph: EvidenceGraph,
        new_node: EvidenceNode,
        existing_claims: list[EvidenceClaim],
    ) -> list[EvidenceClaim]:
        return self.build_claims(graph)


class ConfidenceEngine:
    def score_claim(self, claim: EvidenceClaim, graph: EvidenceGraph) -> ConfidenceProfile:
        nodes = {node.node_id: node for node in graph.nodes}
        support_nodes = [nodes[node_id] for node_id in claim.supporting_node_ids if node_id in nodes]
        opposing_nodes = [nodes[node_id] for node_id in claim.opposing_node_ids if node_id in nodes]
        support_weights = [_node_weight(node) for node in support_nodes]
        opposition_weights = [_node_weight(node) for node in opposing_nodes]
        support_strength = saturated_sum(support_weights)
        opposition_strength = saturated_sum(opposition_weights)
        uncertainty = _uncertainty(support_nodes, opposing_nodes)
        score = sigmoid(logit(0.45) + 1.5 * support_strength - 1.2 * opposition_strength - 0.8 * uncertainty)
        label = _label(score, opposition_strength)
        reasons = [
            f"被 {len(support_nodes)} 个节点支持",
            f"存在 {len(opposing_nodes)} 个相反否认节点",
        ]
        if support_nodes:
            reasons.append("支持来源包含 " + "、".join(sorted({node.source_type for node in support_nodes})))
        if len(support_nodes) <= 1:
            reasons.append("缺少多源独立印证")
        if 0.50 <= score < 0.70:
            reasons.append("进入争议事实区间，建议补强")
        return ConfidenceProfile(
            extraction_quality=sum((node.confidence for node in support_nodes), 0.0) / max(1, len(support_nodes)),
            source_reliability=sum(support_weights) / max(1, len(support_weights)),
            corroboration_score=support_strength,
            contradiction_score=opposition_strength,
            independence_score=min(1.0, len({node.source_material_id for node in support_nodes}) / 3),
            uncertainty=uncertainty,
            final_score=round(score, 4),
            label=label,
            reasons=reasons,
        )

    def score_claims(self, graph: EvidenceGraph) -> list[EvidenceClaim]:
        claims = graph.claims or ClaimBuilder().build_claims(graph)
        return [replace(claim, confidence_profile=self.score_claim(claim, graph)) for claim in claims]


def saturated_sum(weights: list[float]) -> float:
    return 1 - math.exp(-sum(max(0.0, weight) for weight in weights))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def logit(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return math.log(p / (1 - p))


def _node_weight(node: EvidenceNode) -> float:
    source = SOURCE_RELIABILITY.get(node.source_type, 0.50)
    party = PARTY_RELIABILITY.get(node.source_party or "unknown", 0.50)
    return max(0.0, min(1.0, (source + party + node.confidence) / 3))


def _uncertainty(support_nodes: list[EvidenceNode], opposing_nodes: list[EvidenceNode]) -> float:
    value = 0.0
    all_nodes = support_nodes + opposing_nodes
    if any(node.confidence < 0.75 for node in all_nodes):
        value += 0.15
    if len(support_nodes) == 1:
        value += 0.20
    if opposing_nodes:
        value += 0.20
    if any(not node.source_party or node.source_party == "unknown" for node in all_nodes):
        value += 0.10
    if support_nodes and all(node.source_type == "statement" for node in support_nodes):
        value += 0.20
    return min(1.0, value)


def _label(score: float, opposition_strength: float) -> str:
    if score >= 0.85 and opposition_strength < 0.25:
        return "多源较强印证"
    if score >= 0.70:
        return "有一定印证"
    if score >= 0.50:
        return "争议事实，尚不足以否定"
    if score >= 0.35:
        return "明显存疑，需补强"
    return "低可信或被冲突削弱"


def _safe(text: str) -> str:
    return re.sub(r"\W+", "", text or "unknown")[:24] or "unknown"


def _edge_ids_by_node(graph: EvidenceGraph) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for edge in graph.edges:
        for node_id in (edge.source_node_id, edge.target_node_id):
            result.setdefault(node_id, []).append(edge.edge_id)
    return result
