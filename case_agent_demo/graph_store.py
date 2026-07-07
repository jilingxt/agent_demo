from __future__ import annotations

from case_agent_demo.models import EvidenceEdge, EvidenceGraph, EvidenceNode


class GraphStoreTool:
    def __init__(self) -> None:
        self.nodes: dict[str, EvidenceNode] = {}
        self.edges: dict[str, EvidenceEdge] = {}

    def upsert_node(self, node: EvidenceNode) -> EvidenceNode:
        self.nodes[node.node_id] = node
        return node

    def upsert_edge(self, edge: EvidenceEdge) -> EvidenceEdge:
        self.edges[edge.edge_id] = edge
        return edge

    def list_nodes(self) -> list[EvidenceNode]:
        return list(self.nodes.values())

    def list_edges(self) -> list[EvidenceEdge]:
        return list(self.edges.values())

    def to_graph(self) -> EvidenceGraph:
        return EvidenceGraph(nodes=self.list_nodes(), edges=self.list_edges())
