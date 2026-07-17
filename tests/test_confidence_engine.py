import unittest

from case_agent_demo.confidence import ClaimBuilder, ConfidenceEngine
from case_agent_demo.models import CaseGraph, Fact


class ConfidenceEngineTests(unittest.TestCase):
    def test_support_report_raises_score_and_opposition_does_not_zero_it(self):
        def fact(fact_id, source, stance):
            return Fact(fact_id, source, "statement", "张三", "结构化行为陈述", object="李四", metadata={"actor": "张三", "target_person": "李四", "predicate": "violence", "stance": stance, "source_group": source, "origin_evidence": source})

        weak_graph = CaseGraph(facts=[fact("F1", "S1", "affirm")])
        stronger_graph = CaseGraph(
            facts=[fact("F1", "S1", "affirm"), fact("F2", "S2", "affirm")]
        )
        contested_graph = CaseGraph(
            facts=[
                fact("F1", "S1", "affirm"),
                fact("F2", "S2", "affirm"),
                fact("F3", "S3", "deny"),
            ]
        )

        weak_claim = ConfidenceEngine().score_claims(CaseGraph(nodes=weak_graph.nodes))[0]
        scored_claims = ConfidenceEngine().score_claims(CaseGraph(nodes=stronger_graph.nodes))
        contested = ConfidenceEngine().score_claims(CaseGraph(nodes=contested_graph.nodes))[0]

        self.assertGreater(max(claim.confidence_profile.final_score for claim in scored_claims), weak_claim.confidence_profile.final_score)
        self.assertTrue(all(claim.confidence_profile.final_score > 0 for claim in scored_claims))
        self.assertTrue(all(claim.confidence_profile.reasons for claim in scored_claims))
        self.assertGreater(contested.confidence_profile.contradiction_score, 0)
        self.assertGreater(contested.confidence_profile.final_score, 0)

    def test_claim_builder_groups_denial_as_opposing_node(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "张三", "拿取陈述", object="手机", metadata={"predicate": "taking_property", "stance": "affirm"}),
                Fact("F2", "S2", "statement", "张三", "否认拿取", object="手机", metadata={"predicate": "taking_property", "stance": "deny"}),
            ]
        )

        claims = ClaimBuilder().build_claims(graph)

        self.assertTrue(any(claim.supporting_node_ids and claim.opposing_node_ids for claim in claims))

    def test_claim_builder_keeps_ambiguous_node_out_of_support_and_opposition(self):
        graph = CaseGraph(
            facts=[
                Fact(
                    "F1",
                    "S1",
                    "statement",
                    "",
                    "语义模型未能形成确定断言",
                    metadata={
                        "predicate": "unresolved_observation",
                        "stance": "ambiguous",
                    },
                )
            ]
        )

        claim = ClaimBuilder().build_claims(graph)[0]

        self.assertEqual(claim.supporting_node_ids, [])
        self.assertEqual(claim.opposing_node_ids, [])
        self.assertEqual(len(claim.ambiguous_node_ids), 1)


if __name__ == "__main__":
    unittest.main()
