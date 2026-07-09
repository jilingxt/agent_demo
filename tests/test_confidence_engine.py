import unittest

from case_agent_demo.confidence import ClaimBuilder, ConfidenceEngine
from case_agent_demo.models import CaseGraph, Fact


class ConfidenceEngineTests(unittest.TestCase):
    def test_support_report_raises_score_and_opposition_does_not_zero_it(self):
        weak_graph = CaseGraph(facts=[Fact("F1", "S1", "statement", "张三", "张三殴打李四", object="李四")])
        stronger_graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "张三", "张三殴打李四", object="李四"),
                Fact("F2", "R1", "report_image", "李四", "鉴定意见显示李四轻伤二级", object="李四 轻伤二级"),
                Fact("F3", "S2", "statement", "张三", "张三称没有殴打李四", object="李四"),
            ]
        )

        weak_claim = ConfidenceEngine().score_claims(CaseGraph(nodes=weak_graph.nodes))[0]
        scored_claims = ConfidenceEngine().score_claims(CaseGraph(nodes=stronger_graph.nodes))

        self.assertGreater(max(claim.confidence_profile.final_score for claim in scored_claims), weak_claim.confidence_profile.final_score)
        self.assertTrue(all(claim.confidence_profile.final_score > 0 for claim in scored_claims))
        self.assertTrue(all(claim.confidence_profile.reasons for claim in scored_claims))

    def test_claim_builder_groups_denial_as_opposing_node(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "张三", "张三拿走手机", object="手机"),
                Fact("F2", "S2", "statement", "张三", "张三称没有拿走手机", object="手机"),
            ]
        )

        claims = ClaimBuilder().build_claims(graph)

        self.assertTrue(any(claim.supporting_node_ids and claim.opposing_node_ids for claim in claims))


if __name__ == "__main__":
    unittest.main()
