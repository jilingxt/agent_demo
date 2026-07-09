from __future__ import annotations

from dataclasses import replace

from case_agent_demo.models import EvidenceEdge, EvidenceGraph, EvidenceNode


class GraphStoreTool:
    def __init__(self) -> None:
        self.nodes: dict[str, EvidenceNode] = {}
        self.edges: dict[str, EvidenceEdge] = {}

    def add_node(self, node: EvidenceNode) -> EvidenceNode:
        self.nodes[node.node_id] = node
        return node

    def update_node(self, node_id: str, patch: dict) -> EvidenceNode:
        node = self.nodes[node_id]
        updated = replace(node, **patch)
        self.nodes[node_id] = updated
        return updated

    def delete_node(self, node_id: str, soft_delete: bool = True) -> None:
        if soft_delete:
            self.update_node(node_id, {"status": "deleted"})
        else:
            self.nodes.pop(node_id, None)

    def get_node(self, node_id: str) -> EvidenceNode | None:
        return self.nodes.get(node_id)

    def add_edge(self, edge: EvidenceEdge) -> EvidenceEdge:
        self.edges[edge.edge_id] = edge
        return edge

    def update_edge(self, edge_id: str, patch: dict) -> EvidenceEdge:
        edge = self.edges[edge_id]
        updated = replace(edge, **patch)
        self.edges[edge_id] = updated
        return updated

    def delete_edge(self, edge_id: str, soft_delete: bool = True) -> None:
        if soft_delete:
            self.update_edge(edge_id, {"status": "deleted"})
        else:
            self.edges.pop(edge_id, None)

    def get_edge(self, edge_id: str) -> EvidenceEdge | None:
        return self.edges.get(edge_id)

    def list_nodes(self, filters: dict | None = None) -> list[EvidenceNode]:
        return [node for node in self.nodes.values() if _matches(node, filters) and node.status != "deleted"]

    def list_edges(self, filters: dict | None = None) -> list[EvidenceEdge]:
        return [edge for edge in self.edges.values() if _matches(edge, filters) and edge.status != "deleted"]

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[EvidenceNode]:
        neighbors: list[EvidenceNode] = []
        for edge in self.list_edges({"edge_type": edge_type} if edge_type else None):
            target_id = ""
            if edge.source_node_id == node_id:
                target_id = edge.target_node_id
            elif edge.target_node_id == node_id:
                target_id = edge.source_node_id
            if target_id and target_id in self.nodes and self.nodes[target_id].status != "deleted":
                neighbors.append(self.nodes[target_id])
        return neighbors

    def find_edges_between(self, left_id: str, right_id: str) -> list[EvidenceEdge]:
        return [
            edge
            for edge in self.list_edges()
            if {edge.source_node_id, edge.target_node_id} == {left_id, right_id}
        ]

    def to_graph(self) -> EvidenceGraph:
        return EvidenceGraph(nodes=self.list_nodes(), edges=self.list_edges())

    upsert_node = add_node
    upsert_edge = add_edge


def _matches(item: object, filters: dict | None) -> bool:
    if not filters:
        return True
    return all(value is None or getattr(item, key, None) == value for key, value in filters.items())
