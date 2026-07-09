import unittest

from case_agent_demo.models import CaseGraph, ConfidenceProfile, EvidenceClaim, Fact, fact_to_node


class ModelConfidenceClaimTests(unittest.TestCase):
    def test_fact_to_node_infers_polarity_and_claim_type(self):
        denied = fact_to_node(Fact("F1", "S1", "statement", "张三", "张三称没有殴打李四", object="李四"))
        injury = fact_to_node(Fact("F2", "R1", "report_image", "李四", "鉴定意见显示李四轻伤二级", object="李四 轻伤二级"))

        self.assertEqual(denied.polarity, "deny")
        self.assertEqual(denied.claim_type, "violence")
        self.assertEqual(injury.polarity, "affirm")
        self.assertEqual(injury.claim_type, "injury_consequence")

    def test_case_graph_preserves_fact_node_claim_compatibility(self):
        fact = Fact("F1", "S1", "statement", "张三", "张三拿走手机", object="手机")
        graph = CaseGraph(facts=[fact], claims=[EvidenceClaim("CL-taking-张三-手机", "张三", "taking_property", "手机")])

        self.assertEqual(graph.nodes[0].node_id, "F1")
        self.assertEqual(graph.facts[0].fact_id, "F1")
        self.assertEqual(graph.claims[0].behavior_type, "taking_property")

    def test_confidence_profile_can_explain_score(self):
        profile = ConfidenceProfile(final_score=0.66, label="争议事实，尚不足以否定", reasons=["存在相反否认节点"])

        self.assertEqual(profile.label, "争议事实，尚不足以否定")
        self.assertTrue(profile.reasons)


if __name__ == "__main__":
    unittest.main()
