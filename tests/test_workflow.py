import unittest

from case_agent_demo.workflow import CaseWorkflow, HumanConfirmationRequired
from case_agent_demo.models import Material, MaterialType


class CaseWorkflowTests(unittest.TestCase):
    def test_requires_human_case_type_before_execution(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material(
                material_id="S1",
                material_type=MaterialType.STATEMENT,
                content="被询问人张三称其没有到过现场。",
            )
        ]

        suggestion = workflow.suggest_case_type(materials)

        self.assertTrue(suggestion.requires_human_confirmation)
        with self.assertRaises(HumanConfirmationRequired):
            workflow.run(materials)

    def test_confirmed_run_records_material_plan_before_extraction(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material("S1", MaterialType.STATEMENT, "张三称20时在家。", "vault/statements/S1.txt"),
            Material("S2", MaterialType.STATEMENT, "李四称20时在现场。", "vault/statements/S2.txt"),
            Material("P1", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/group_a/1.jpg"),
            Material("P2", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/group_a/2.jpg"),
        ]

        result = workflow.run(materials, confirmed_case_type="盗窃类案件")

        self.assertIn("planning_agent_material_plan", result.executed_agents)
        self.assertEqual(result.material_plan.statement_count, 2)
        self.assertEqual(result.material_plan.evidence_image_group_count, 1)

    def test_workflow_dispatches_image_folder_as_one_group_when_vision_tool_is_available(self):
        class RecordingVisionTool:
            def __init__(self):
                self.group_calls = []

            def describe_group(self, group_id, image_paths):
                self.group_calls.append((group_id, list(image_paths)))
                from case_agent_demo.vision_tools import ImageEvidenceDescription

                return ImageEvidenceDescription(pic=f"{group_id} image description", text="", confidence=0.95)

        workflow = CaseWorkflow.demo()
        vision_tool = RecordingVisionTool()
        workflow.pic_agent.vision_tool = vision_tool
        materials = [
            Material("S1", MaterialType.STATEMENT, "张三称20时在家。", "vault/statements/S1.txt"),
            Material("P1", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/group_a/1.jpg"),
            Material("P2", MaterialType.EVIDENCE_IMAGE, "needs qwen", "vault/identification_images/group_a/2.jpg"),
        ]

        result = workflow.run(materials, confirmed_case_type="盗窃类案件")

        self.assertEqual(vision_tool.group_calls, [("group_a", ["vault/identification_images/group_a/1.jpg", "vault/identification_images/group_a/2.jpg"])])
        self.assertIn("pic_agent_group", result.executed_agents)
        self.assertNotIn("pic_agent", result.executed_agents)

    def test_confirmed_case_type_runs_report_image_agent_and_builds_report(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material(
                material_id="S1",
                material_type=MaterialType.STATEMENT,
                content="张三称20时在家，李四称20时看见张三在现场。",
            ),
            Material(
                material_id="P1",
                material_type=MaterialType.EVIDENCE_IMAGE,
                content="现场照片显示一名男子和被损坏门锁。",
            ),
            Material(
                material_id="R1",
                material_type=MaterialType.REPORT_IMAGE,
                content="监控研判报告：20时05分张三出现在现场附近。签章清晰。",
            ),
        ]

        result = workflow.run(materials, confirmed_case_type="盗窃类案件")

        self.assertEqual(result.confirmed_case_type, "盗窃类案件")
        self.assertIn("report_image_agent", result.executed_agents)
        self.assertGreaterEqual(len(result.case_graph.facts), 3)
        self.assertTrue(result.conflicts)
        self.assertTrue(result.challenges)
        self.assertIn("case_graph_agent", result.executed_agents)
        self.assertIn("judge_agent", result.executed_agents)
        self.assertEqual(result.review.status, "PASS")
        self.assertIn("现有证据显示", result.report)
        self.assertIn("反方质询", result.report)
        self.assertNotIn("已经构成犯罪", result.report)

    def test_legal_retrieval_is_shared_tool_not_workflow_agent(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material("S1", MaterialType.STATEMENT, "张三称20时在家。"),
            Material("R1", MaterialType.REPORT_IMAGE, "监控研判报告：20时05分张三出现在现场附近。签章清晰。"),
        ]

        result = workflow.run(materials, confirmed_case_type="盗窃类案件")

        self.assertTrue(hasattr(workflow, "legal_tool"))
        self.assertFalse(hasattr(workflow, "rag_agent"))
        self.assertNotIn("rag_legal_agent", result.executed_agents)
        self.assertIn("legal_retrieval_tool", result.executed_agents)
        self.assertTrue(result.legal_matches)
        self.assertFalse(hasattr(workflow.legal_tool, "ingest"))

    def test_selected_agents_can_share_legal_retrieval_tool(self):
        workflow = CaseWorkflow.demo()

        self.assertIs(workflow.report_image_agent.legal_tool, workflow.legal_tool)
        self.assertIs(workflow.evidence_graph_agent.legal_tool, workflow.legal_tool)
        self.assertIs(workflow.reasoning_agent.legal_tool, workflow.legal_tool)
        self.assertIs(workflow.judge_agent.legal_tool, workflow.legal_tool)
        self.assertIs(workflow.review_agent.legal_tool, workflow.legal_tool)

    def test_review_rejects_final_legal_judgment(self):
        workflow = CaseWorkflow.demo()

        review = workflow.review_agent.review(
            report="张三已经构成犯罪，应当处罚。",
            supporting_fact_ids=["F1"],
            supporting_law_ids=["L1"],
        )

        self.assertEqual(review.status, "FAIL")
        self.assertTrue(any("最终性法律判断" in item for item in review.issues))

    def test_report_image_agent_does_not_include_time_suffix_in_person_name(self):
        workflow = CaseWorkflow.demo()
        material = Material(
            material_id="R1",
            material_type=MaterialType.REPORT_IMAGE,
            content="监控研判报告：20时05分张三出现在现场附近。签章清晰。",
        )

        facts = workflow.report_image_agent.extract(material)

        self.assertEqual(facts[0].person, "张三")

    def test_model_profiles_use_dsv4_for_text_and_qwen_for_vision(self):
        workflow = CaseWorkflow.demo()

        self.assertEqual(workflow.model_profiles.planning.model_name, "deepseek-v4-pro")
        self.assertEqual(workflow.model_profiles.reasoning.model_name, "deepseek-v4-pro")
        self.assertEqual(workflow.model_profiles.judge.model_name, "deepseek-v4-pro")
        self.assertEqual(workflow.model_profiles.review.model_name, "deepseek-v4-pro")
        self.assertEqual(workflow.model_profiles.text.model_name, "deepseek-v4-flash")
        self.assertEqual(workflow.model_profiles.database.model_name, "deepseek-v4-flash")
        self.assertEqual(workflow.model_profiles.vision.model_name, "qwen2.5-vl-72b-instruct")
        self.assertEqual(workflow.model_profiles.vision.provider, "qwen")

    def test_vision_profile_uses_qwen_input(self):
        workflow = CaseWorkflow.demo()

        self.assertIn("external_qwen_result", workflow.model_profiles.vision.input_mode)

    def test_judge_challenges_high_conflict_before_review(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material("S1", MaterialType.STATEMENT, "张三称20时在家。"),
            Material("R1", MaterialType.REPORT_IMAGE, "监控研判报告：20时05分张三出现在现场附近。签章清晰。"),
        ]

        result = workflow.run(materials, confirmed_case_type="盗窃类案件")

        self.assertTrue(any(item.challenge_type == "unresolved_conflict" for item in result.challenges))
        self.assertIn("需人工确认", result.final_report)

    def test_judge_challenges_case_type_when_property_damage_type_has_only_injury_facts(self):
        workflow = CaseWorkflow.demo()
        materials = [
            Material(
                "S1",
                MaterialType.STATEMENT,
                "被询问人李文杰称：2026年6月12日20时许，在深圳市宝安区新凯飞汽配，我拉拽贺显作衣领并抱摔，导致贺显作鼻骨骨折。",
            ),
            Material(
                "R1",
                MaterialType.REPORT_IMAGE,
                "法医鉴定报告：被鉴定人贺显作所受损伤为双侧鼻骨骨折、轻伤二级。鉴定意见明确。",
            ),
        ]

        result = workflow.run(materials, confirmed_case_type="故意毁坏财物类案件")

        self.assertTrue(any(item.challenge_type == "case_type_mismatch" for item in result.challenges))
        self.assertIn("案件类型", result.final_report)


if __name__ == "__main__":
    unittest.main()
