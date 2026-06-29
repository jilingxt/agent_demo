import unittest

from case_agent_demo.agents import PicAgent, ReasoningAgent, TextAgent
from case_agent_demo.models import CaseGraph, Conflict, Fact, LegalMatch, Material, MaterialType


class RecordingRuntime:
    def __init__(self):
        self.calls = []

    def run_json(self, prompt_name, profile, user_input, fallback, parser):
        self.calls.append(user_input)
        return fallback()


class ContextIsolationTests(unittest.TestCase):
    def test_text_agent_sends_only_one_statement_to_runtime(self):
        runtime = RecordingRuntime()
        agent = TextAgent(runtime=runtime)
        first = Material("S1", MaterialType.STATEMENT, "张三称20时在家。")
        second = Material("S2", MaterialType.STATEMENT, "李四称20时在现场。")

        first_facts = agent.extract(first)
        second_facts = agent.extract(second)

        self.assertEqual(len(runtime.calls), 2)
        self.assertIn("张三", runtime.calls[0])
        self.assertNotIn("李四", runtime.calls[0])
        self.assertIn("李四", runtime.calls[1])
        self.assertNotIn("张三", runtime.calls[1])
        self.assertTrue(all(isinstance(fact, Fact) for fact in first_facts + second_facts))
        self.assertEqual(first_facts[0].source_material_id, "S1")
        self.assertEqual(second_facts[0].source_material_id, "S2")

    def test_pic_agent_describes_only_one_image_group_at_a_time(self):
        class RecordingVisionTool:
            def __init__(self):
                self.calls = []

            def describe_group(self, group_id, image_paths):
                self.calls.append((group_id, list(image_paths)))
                from case_agent_demo.vision_tools import ImageEvidenceDescription

                return ImageEvidenceDescription(pic=f"{group_id} description", text="", confidence=0.95)

        vision_tool = RecordingVisionTool()
        agent = PicAgent(vision_tool=vision_tool)

        facts = agent.extract_group("group_a", ["vault/identification_images/group_a/1.jpg", "vault/identification_images/group_a/2.jpg"])

        self.assertEqual(vision_tool.calls, [("group_a", ["vault/identification_images/group_a/1.jpg", "vault/identification_images/group_a/2.jpg"])])
        self.assertEqual(facts[0].source_material_id, "group_a")
        self.assertIn("group_a description", facts[0].behavior)

    def test_reasoning_agent_runtime_input_is_limited_to_structured_evidence(self):
        runtime = RecordingRuntime()
        agent = ReasoningAgent(runtime=runtime)
        payload = {
            "confirmed_case_type": "盗窃类案件",
            "evidence_graph": CaseGraph(
                facts=[Fact("F1", "S1", "statement", "张三", "张三称20时在家。")]
            ),
            "legal_matches": [
                LegalMatch("L1", "law", "article", "element", "behavior", "source")
            ],
            "conflicts": [
                Conflict("C1", "presence_conflict", "a", "b", "S1", "R1", "high")
            ],
        }

        agent.reason(payload)

        self.assertEqual(len(runtime.calls), 1)
        self.assertIn("case_graph_facts", runtime.calls[0])
        self.assertIn("legal_matches", runtime.calls[0])
        self.assertIn("conflicts", runtime.calls[0])
        self.assertNotIn("raw_materials", runtime.calls[0])


if __name__ == "__main__":
    unittest.main()
