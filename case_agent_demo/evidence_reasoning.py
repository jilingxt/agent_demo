from __future__ import annotations

import re
from dataclasses import replace

from case_agent_demo.models import EvidenceAssertion, EvidenceClaim, EvidenceGraph, infer_claim_type


class AssertionNormalizer:
    def normalize_graph(self, graph: EvidenceGraph) -> list[EvidenceAssertion]:
        return [self.normalize_node(node) for node in graph.nodes if node.node_type == "fact" and node.status == "active"]

    def normalize_node(self, node) -> EvidenceAssertion:
        metadata = node.metadata
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
            key = (
                assertion.actor,
                assertion.predicate,
                target,
                assertion.event_id,
            )
            claim = buckets.get(key) or EvidenceClaim(
                claim_id=_claim_id(key),
                subject=assertion.actor,
                behavior_type=assertion.predicate,
                object=assertion.object,
                target_person=assertion.target_person,
                event_id=assertion.event_id,
            )
            claim = replace(claim, assertion_ids=[*claim.assertion_ids, assertion.assertion_id])
            if assertion.stance == "affirm":
                claim = replace(claim, supporting_node_ids=[*claim.supporting_node_ids, assertion.node_id])
            elif assertion.stance == "deny":
                claim = replace(claim, opposing_node_ids=[*claim.opposing_node_ids, assertion.node_id])
            else:
                claim = replace(claim, ambiguous_node_ids=[*claim.ambiguous_node_ids, assertion.node_id])
            buckets[key] = claim
        return list(buckets.values())


def _normalize_stance(stance: str) -> str:
    if stance in {"affirm", "support"}:
        return "affirm"
    if stance in {"deny", "oppose"}:
        return "deny"
    return "ambiguous"


def _claim_id(key: tuple[str, str, str, str]) -> str:
    return "CL-" + "-".join(_safe(part) for part in (key[1], key[0], key[2], key[3]))


def _safe(value: str) -> str:
    return re.sub(r"\W+", "", value or "unknown")[:24] or "unknown"
