from __future__ import annotations

from case_agent_demo.models import EvidenceEdge, EvidenceNode


class RelationRuleTool:
    def infer_edges_for_new_node(
        self,
        new_node: EvidenceNode,
        existing_nodes: list[EvidenceNode],
    ) -> list[EvidenceEdge]:
        edges: list[EvidenceEdge] = []
        if new_node.confidence < 0.75:
            edges.append(
                EvidenceEdge(
                    edge_id=f"E-{new_node.node_id}-needs-human-check",
                    source_node_id=new_node.node_id,
                    target_node_id=new_node.node_id,
                    edge_type="needs_human_check",
                    reason="节点置信度低于 0.75，需要人工复核。",
                    confidence=1.0,
                    evidence_basis=[new_node.node_id],
                )
            )

        for old_node in existing_nodes:
            if old_node.node_id == new_node.node_id:
                continue
            edges.extend(self._pair_edges(new_node, old_node))
        return edges

    def _pair_edges(self, new_node: EvidenceNode, old_node: EvidenceNode) -> list[EvidenceEdge]:
        edges: list[EvidenceEdge] = []
        pair_id = f"{old_node.node_id}-{new_node.node_id}"
        if new_node.person and new_node.person == old_node.person:
            edges.append(_edge(pair_id, old_node, new_node, "same_person", "涉及同一人员。"))
        if _overlaps(new_node.object, old_node.object):
            edges.append(_edge(pair_id, old_node, new_node, "same_object", "涉及同一对象或后果。"))
        if _same_event(new_node, old_node):
            edges.append(_edge(pair_id, old_node, new_node, "same_event", "人员、对象、时间、地点至少两个维度重合。"))
        if _is_contradiction(new_node, old_node):
            edges.append(_edge(pair_id, old_node, new_node, "contradicts", "否认事实与正向事实在同一对象上冲突。", 0.9))
        elif _supports(new_node, old_node):
            edges.append(_edge(pair_id, old_node, new_node, "supports", "报告或图片事实与既有事实相互印证。"))
        return edges


def _edge(
    pair_id: str,
    source: EvidenceNode,
    target: EvidenceNode,
    edge_type: str,
    reason: str,
    confidence: float = 0.8,
) -> EvidenceEdge:
    return EvidenceEdge(
        edge_id=f"E-{pair_id}-{edge_type}",
        source_node_id=source.node_id,
        target_node_id=target.node_id,
        edge_type=edge_type,
        reason=reason,
        confidence=confidence,
        evidence_basis=[source.node_id, target.node_id],
    )


def _overlaps(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left in right or right in left


def _same_event(left: EvidenceNode, right: EvidenceNode) -> bool:
    matches = 0
    for attr in ("person", "object", "time", "location"):
        left_value = getattr(left, attr)
        right_value = getattr(right, attr)
        if left_value and right_value and (left_value == right_value or left_value in right_value or right_value in left_value):
            matches += 1
    return matches >= 2


def _is_denial(node: EvidenceNode) -> bool:
    return any(word in f"{node.summary}{node.behavior}" for word in ("没有", "未", "否认", "不承认", "没"))


def _is_contradiction(left: EvidenceNode, right: EvidenceNode) -> bool:
    if _is_denial(left) == _is_denial(right):
        return False
    if not (_overlaps(left.object, right.object) or (left.person and left.person == right.person)):
        return False
    return True


def _supports(left: EvidenceNode, right: EvidenceNode) -> bool:
    source_types = {left.source_type, right.source_type}
    if not ({"report_image", "evidence_image"} & source_types):
        return False
    return not _is_contradiction(left, right) and (
        _overlaps(left.object, right.object) or (left.person and left.person == right.person)
    )
