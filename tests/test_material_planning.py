import unittest

from case_agent_demo.agents import PlanningAgent
from case_agent_demo.material_plan import MaterialPlan
from case_agent_demo.models import Material, MaterialType


class MaterialPlanningTests(unittest.TestCase):
    def test_builds_separate_statement_tasks_and_image_group_tasks(self):
        materials = [
            Material("S-one", MaterialType.STATEMENT, "statement one", "vault/statements/one.txt"),
            Material("S-two", MaterialType.STATEMENT, "statement two", "vault/statements/two.txt"),
            Material("P-group_a-1", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/group_a/1.jpg"),
            Material("P-group_a-2", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/group_a/2.jpg"),
            Material("P-single", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/single.jpg"),
            Material("R-report_a-1", MaterialType.REPORT_IMAGE, "needs qwen", "vault/report_images/report_a/page1.png"),
        ]

        plan = MaterialPlan.from_materials(materials)

        self.assertEqual(plan.statement_count, 2)
        self.assertEqual(plan.evidence_image_group_count, 2)
        self.assertEqual(plan.report_image_group_count, 1)
        self.assertEqual([task.material_ids for task in plan.statement_tasks], [["S-one"], ["S-two"]])
        self.assertEqual(
            {task.group_id: task.material_ids for task in plan.evidence_image_tasks},
            {
                "group_a": ["P-group_a-1", "P-group_a-2"],
                "single": ["P-single"],
            },
        )
        self.assertTrue(all(task.requires_vision for task in plan.image_tasks))

    def test_planning_agent_exposes_material_plan_before_execution(self):
        materials = [
            Material("S-one", MaterialType.STATEMENT, "statement one", "vault/statements/one.txt"),
            Material("P-one", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/group_a/1.jpg"),
        ]

        plan = PlanningAgent().plan_materials(materials)

        self.assertEqual(plan.total_materials, 2)
        self.assertEqual(plan.statement_count, 1)
        self.assertEqual(plan.evidence_image_group_count, 1)


if __name__ == "__main__":
    unittest.main()
