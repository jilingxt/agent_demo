import unittest

from case_agent_demo.graph_store import GraphStoreTool
from case_agent_demo.models import EvidenceEdge, Fact, fact_to_node


class GraphStoreCrudTests(unittest.TestCase):
    def test_node_edge_crud_and_queries(self):
        store = GraphStoreTool()
        left = store.add_node(fact_to_node(Fact("F1", "S1", "statement", "张三", "张三拿走手机", object="手机")))
        right = store.add_node(fact_to_node(Fact("F2", "P1", "evidence_image", "张三", "监控显示张三拿走手机", object="手机")))
        edge = store.add_edge(EvidenceEdge("E1", left.node_id, right.node_id, "supports", "相互印证"))

        self.assertIsNotNone(store.get_node("F1"))
        self.assertEqual(store.neighbors("F1"), [right])
        self.assertEqual(store.find_edges_between("F1", "F2"), [edge])

        updated = store.update_node("F1", {"status": "archived"})
        self.assertEqual(updated.status, "archived")
        store.delete_edge("E1")
        self.assertEqual(store.get_edge("E1").status, "deleted")
        self.assertEqual(store.list_edges(), [])


if __name__ == "__main__":
    unittest.main()
