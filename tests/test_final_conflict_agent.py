import unittest

from case_agent_demo.confidence import ConfidenceEngine
from case_agent_demo.final_conflict_agent import FinalConflictAgent, issues_to_challenges
from case_agent_demo.models import (
    CaseGraph,
    ClaimAssessment,
    ClaimOpinion,
    EvidenceClaim,
    EvidenceEdge,
    Fact,
    LegalRAGResult,
)


class FinalConflictAgentTests(unittest.TestCase):
    def test_legacy_full_node_values_only_review_registered_derived_nodes(self):
        rag = LegalRAGResult(matches=[], chunks=[], query="", purpose="final_review")

        issues = FinalConflictAgent().review(
            "一般案件",
            CaseGraph(),
            "",
            rag,
            bayesian_result={
                "node_values": {
                    "conduct": 0.1,
                    "result_exists": 0.1,
                    "causation": 0.8,
                }
            },
        )

        assert not any(issue.issue_type == "derived_fact_insufficient" for issue in issues)
        assert not any(issue.issue_type == "causation_insufficient" for issue in issues)

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

    def test_claim_assessments_and_bayesian_causation_drive_challenges(self):
        injury_claim = EvidenceClaim("C-INJURY", "李四", "injury_grade")
        violence_claim = EvidenceClaim("C-VIOLENCE", "张三", "violence", target_person="李四")
        graph = CaseGraph(claims=[injury_claim, violence_claim])
        assessments = [
            ClaimAssessment(
                claim_id="C-INJURY",
                status="authority_anchored",
                opinion=ClaimOpinion("C-INJURY", support=0.95, uncertainty=0.05),
            ),
            ClaimAssessment(
                claim_id="C-VIOLENCE",
                status="contested",
                opinion=ClaimOpinion(
                    "C-VIOLENCE", support=0.4, opposition=0.3, uncertainty=0.3, conflict=0.8
                ),
            ),
        ]
        rag = LegalRAGResult(matches=[], chunks=[], query="", purpose="final_review")

        issues = FinalConflictAgent().review(
            "故意伤害",
            graph,
            "",
            rag,
            claim_assessments=assessments,
            bayesian_result={"node_values": {"causation": 0.35}},
        )

        issue_types = {issue.issue_type for issue in issues}
        self.assertIn("contested_but_not_refuted", issue_types)
        self.assertIn("causation_insufficient", issue_types)


if __name__ == "__main__":
    unittest.main()
