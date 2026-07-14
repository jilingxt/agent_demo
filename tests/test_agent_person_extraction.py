import unittest

from case_agent_demo.agents import ReportImageAgent, TextAgent
from case_agent_demo.models import Material, MaterialType
from tests.semantic_runtime import SemanticFixtureRuntime, semantic_fact


class AgentPersonExtractionTests(unittest.TestCase):
    def test_text_agent_uses_interviewee_name_in_statement(self):
        material = Material(
            "S-test",
            MaterialType.STATEMENT,
            "询问地点 某派出所\n被询问人 王明华\n问：你说一下自己的个人信息？\n答：我叫王明华。\n问：事情经过？\n答：李志强拉我衣领并将我抱摔在地。",
        )

        facts = TextAgent(
            runtime=SemanticFixtureRuntime(
                {"S-test": [semantic_fact(actor="李志强", target_person="王明华", predicate="physical_contact", behavior="李志强对王明华实施身体接触", declarant="王明华")]}
            )
        ).extract(material)

        self.assertEqual(facts[0].person, "王明华")

    def test_report_agent_uses_examined_person_in_forensic_report(self):
        material = Material(
            "R-forensic",
            MaterialType.REPORT_IMAGE,
            "司法鉴定意见书\n被鉴定人：王明华，男，44岁。\n鉴定意见：被鉴定人王明华所受的损伤为轻伤二级。",
        )

        facts = ReportImageAgent(
            runtime=SemanticFixtureRuntime(
                {"R-forensic": [semantic_fact(actor="王明华", predicate="injury_grade", behavior="王明华的损伤被评定为轻伤二级", declarant="王明华", evidence_category="report_image")]}
            )
        ).extract(material)

        self.assertEqual(facts[0].person, "王明华")

    def test_report_agent_uses_suspect_in_video_analysis_report(self):
        material = Material(
            "R-video",
            MaterialType.REPORT_IMAGE,
            "监控研判报告：嫌疑人李志强首先将受害人王明华拉倒在地，后将受害人抱摔在地。",
        )

        facts = ReportImageAgent(
            runtime=SemanticFixtureRuntime(
                {"R-video": [semantic_fact(actor="李志强", target_person="王明华", predicate="physical_contact", behavior="李志强对王明华实施身体接触", declarant="李志强", evidence_category="report_image")]}
            )
        ).extract(material)

        self.assertEqual(facts[0].person, "李志强")


if __name__ == "__main__":
    unittest.main()
