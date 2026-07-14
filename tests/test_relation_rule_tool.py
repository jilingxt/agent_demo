import unittest

from case_agent_demo.models import Fact, fact_to_node
from case_agent_demo.relation_tools import RelationRuleTool


class RelationRuleToolTests(unittest.TestCase):
    def test_same_person_and_same_object_edges_are_generated(self):
        old = fact_to_node(Fact("F1", "S1", "statement", "张三", "张三拿走手机", object="手机"))
        new = fact_to_node(Fact("F2", "P1", "evidence_image", "张三", "监控显示张三拿走手机", object="手机"))

        edges = RelationRuleTool().infer_edges_for_new_node(new, [old])
        edge_types = {edge.edge_type for edge in edges}

        self.assertIn("same_person", edge_types)
        self.assertIn("same_object", edge_types)

    def test_denial_against_affirming_fact_generates_contradiction(self):
        old = fact_to_node(Fact("F1", "S1", "statement", "张三", "否认该行为", object="手机", metadata={"predicate": "taking_property", "stance": "deny"}))
        new = fact_to_node(Fact("F2", "P1", "evidence_image", "张三", "记录该行为", object="手机", metadata={"predicate": "taking_property", "stance": "affirm"}))

        edges = RelationRuleTool().infer_edges_for_new_node(new, [old])

        self.assertTrue(any(edge.edge_type == "contradicts" for edge in edges))

    def test_low_confidence_node_generates_human_check_edge(self):
        node = fact_to_node(Fact("F1", "P1", "evidence_image", "张三", "图片疑似显示张三", confidence=0.5))

        edges = RelationRuleTool().infer_edges_for_new_node(node, [])

        self.assertTrue(any(edge.edge_type == "needs_human_check" for edge in edges))


if __name__ == "__main__":
    unittest.main()
