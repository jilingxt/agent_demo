import unittest

from case_agent_demo.agents import PicAgent
from case_agent_demo.models import Material, MaterialType
from case_agent_demo.vision_tools import ImageEvidenceDescription


class FakeVisionTool:
    def __init__(self) -> None:
        self.materials = []

    def describe(self, material):
        self.materials.append(material)
        return ImageEvidenceDescription(
            pic="图片显示一把被撬坏的门锁和现场地面痕迹",
            text="标签：现场照片1；签名：李四",
            confidence=0.93,
        )


class PicAgentQwenTests(unittest.TestCase):
    def test_pic_agent_uses_qwen_description_for_image_material(self):
        vision_tool = FakeVisionTool()
        agent = PicAgent(vision_tool=vision_tool)
        material = Material(
            material_id="P1",
            material_type=MaterialType.EVIDENCE_IMAGE,
            content="待 Qwen 识别",
            source_path="evidence_vault/identification_images/P1.jpg",
        )

        facts = agent.extract(material)

        self.assertEqual(len(vision_tool.materials), 1)
        self.assertIn("图片显示一把被撬坏的门锁", facts[0].behavior)
        self.assertIn("签名：李四", facts[0].behavior)
        self.assertEqual(facts[0].confidence, 0.93)

    def test_pic_agent_keeps_manual_extracted_content_without_vision_tool_call(self):
        vision_tool = FakeVisionTool()
        agent = PicAgent(vision_tool=vision_tool)
        material = Material(
            material_id="P2",
            material_type=MaterialType.EVIDENCE_IMAGE,
            content="人工录入：图片显示红色背包。",
            source_path="evidence_vault/identification_images/P2.jpg",
        )

        facts = agent.extract(material)

        self.assertEqual(vision_tool.materials, [])
        self.assertIn("人工录入：图片显示红色背包。", facts[0].behavior)


if __name__ == "__main__":
    unittest.main()
