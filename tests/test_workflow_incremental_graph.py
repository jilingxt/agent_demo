import unittest

from case_agent_demo.models import Material, MaterialType
from case_agent_demo.workflow import CaseWorkflow


class WorkflowIncrementalGraphTests(unittest.TestCase):
    def test_workflow_builds_graph_nodes_edges_and_claims_incrementally(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material("S1", MaterialType.STATEMENT, "张三称20时在现场拿走手机。"),
            Material("S2", MaterialType.STATEMENT, "张三称21时在现场归还手机。"),
        ]

        result = workflow.run(materials, confirmed_case_type="盗窃类案件")

        self.assertTrue(result.case_graph.facts)
        self.assertTrue(result.case_graph.nodes)
        self.assertTrue(result.case_graph.edges)
        self.assertTrue(any(edge.edge_type == "source_of" for edge in result.case_graph.edges))
        self.assertTrue(any(edge.edge_type in {"same_person", "same_object", "supports"} for edge in result.case_graph.edges))
        self.assertTrue(result.case_graph.claims)
        self.assertTrue(result.assertions)
        self.assertTrue(result.claim_assessments)
        self.assertEqual(result.bayesian_result["selected_model_ids"], ["property_taking"])
        self.assertIn("evidence_reasoning_engine", result.executed_agents)


    def test_workflow_accepts_explicit_authority_verification_for_forensic_report(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material(
                "R1",
                MaterialType.REPORT_IMAGE,
                "司法鉴定意见书。被鉴定人：李四。鉴定意见：所受损伤为轻伤二级。",
            )
        ]
        verification = {
            "issuer": "qualified_forensic_institution",
            "document_type": "forensic_injury_grade_report",
            "competence_verified": True,
            "authenticity_verified": True,
            "procedure_verified": True,
            "subject_identity_verified": True,
            "method_verified": True,
            "standard_verified": True,
            "scope_verified": True,
            "human_verified": True,
        }

        result = workflow.run(
            materials,
            confirmed_case_type="故意伤害",
            authority_verifications={"F-R1-REPORT": verification},
        )

        self.assertTrue(
            any(item.status == "authority_anchored" for item in result.claim_assessments)
        )
        self.assertIsNone(result.bayesian_result)


if __name__ == "__main__":
    unittest.main()
