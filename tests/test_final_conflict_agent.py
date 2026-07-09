import unittest

from case_agent_demo.confidence import ConfidenceEngine
from case_agent_demo.final_conflict_agent import FinalConflictAgent, issues_to_challenges
from case_agent_demo.models import CaseGraph, EvidenceEdge, Fact, LegalRAGResult


class FinalConflictAgentTests(unittest.TestCase):
    def test_generates_validation_issues_and_challenge_compatibility(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "张三", "张三殴打李四", object="李四"),
                Fact("F2", "S2", "statement", "张三", "张三称没有殴打李四", object="李四"),
                Fact("F3", "P1", "evidence_image", "张三", "图片疑似显示张三在现场", confidence=0.5),
            ],
            edges=[EvidenceEdge("E1", "F1", "F2", "contradicts", "否认与正向事实冲突")],
        )
        graph = CaseGraph(nodes=graph.nodes, edges=graph.edges, claims=ConfidenceEngine().score_claims(graph))
        empty_rag = LegalRAGResult(matches=[], chunks=[], query="故意伤害", purpose="final_review")

        issues = FinalConflictAgent().review("故意伤害类案件", graph, "张三已经构成犯罪", empty_rag)
        issue_types = {issue.issue_type for issue in issues}
        challenges = issues_to_challenges(issues)

        self.assertIn("evidence_conflict", issue_types)
        self.assertIn("legal_basis_missing", issue_types)
        self.assertIn("report_overclaim", issue_types)
        self.assertIn("image_evidence_low_confidence", issue_types)
        self.assertTrue(all(issue.required_action for issue in issues))
        self.assertTrue(challenges)


if __name__ == "__main__":
    unittest.main()
