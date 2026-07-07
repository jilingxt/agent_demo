import unittest

from case_agent_demo.graph_store import GraphStoreTool
from case_agent_demo.models import EvidenceEdge, Fact, fact_to_node


class EvidenceGraphNodesEdgesTests(unittest.TestCase):
    def test_fact_to_node_preserves_fact_fields(self):
        fact = Fact(
            fact_id="F1",
            source_material_id="S1",
            source_type="statement",
            person="张三",
            behavior="张三称没有拿手机",
            time="20时",
            location="现场",
            object="手机",
            confidence=0.84,
            human_confirmed=True,
        )

        node = fact_to_node(fact)

        self.assertEqual(node.node_id, "F1")
        self.assertEqual(node.node_type, "fact")
        self.assertEqual(node.source_material_id, "S1")
        self.assertEqual(node.summary, "张三称没有拿手机")
        self.assertEqual(node.person, "张三")
        self.assertEqual(node.object, "手机")
        self.assertTrue(node.human_confirmed)

    def test_graph_store_upserts_nodes_edges_and_returns_graph(self):
        store = GraphStoreTool()
        node = fact_to_node(Fact("F1", "S1", "statement", "张三", "张三拿走手机", object="手机"))
        edge = EvidenceEdge(
            edge_id="E1",
            source_node_id="S1",
            target_node_id="F1",
            edge_type="source_of",
            reason="材料生成事实节点",
        )

        store.upsert_node(node)
        store.upsert_edge(edge)
        graph = store.to_graph()

        self.assertEqual(graph.nodes, [node])
        self.assertEqual(graph.edges, [edge])
        self.assertEqual(graph.facts[0].fact_id, "F1")


if __name__ == "__main__":
    unittest.main()
