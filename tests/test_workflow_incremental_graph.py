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
        self.assertIn("case_graph_agent", result.executed_agents)


if __name__ == "__main__":
    unittest.main()
