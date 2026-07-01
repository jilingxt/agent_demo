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

    def test_report_documents_are_not_planned_as_qwen_image_tasks(self):
        materials = [
            Material("R-docx", MaterialType.REPORT_IMAGE, "report text", "vault/report_images/report.docx"),
            Material("R-pdf", MaterialType.REPORT_IMAGE, "report text", "vault/report_images/report.pdf"),
            Material("R-img", MaterialType.REPORT_IMAGE, "needs qwen", "vault/report_images/report/page1.jpg"),
        ]

        plan = MaterialPlan.from_materials(materials)

        self.assertEqual(len(plan.report_image_tasks), 1)
        self.assertEqual(plan.report_image_tasks[0].material_ids, ["R-img"])
        self.assertEqual(plan.report_image_tasks[0].source_paths, ["vault/report_images/report/page1.jpg"])

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
