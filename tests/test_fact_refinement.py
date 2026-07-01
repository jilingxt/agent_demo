import unittest

from case_agent_demo.agents import PicAgent, ReasoningAgent, ReportImageAgent, TextAgent
from case_agent_demo.models import CaseGraph, Material, MaterialType
from case_agent_demo.vision_tools import ImageEvidenceDescription


class FactRefinementTests(unittest.TestCase):
    def test_text_agent_extracts_concise_who_did_what_when_where(self):
        content = (
            "询问笔录\n"
            "被询问人 李文杰\n"
            "问：你有没有殴打他人的行为？\n"
            "答：我有。\n"
            "问：你说一下事情经过？\n"
            "答：2026年6月12日17时许，在深圳市宝安区新凯飞汽配，我和同事贺显作发生口角，"
            "我先拉他的衣领，贺显作被我拽倒在地。他站起来之后就用手掐我脖子，"
            "我就抱着贺显作的身体往地上摔，贺显作的眼角当时有肿包流血。\n"
            "问：贺显作的伤是如何造成的？\n"
            "答：是我把他抱摔在地上撞击地面造成的。"
        )
        facts = TextAgent().extract(Material("S-li", MaterialType.STATEMENT, content))

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertEqual(fact.person, "李文杰")
        self.assertIn("抱摔", fact.behavior)
        self.assertIn("贺显作", fact.behavior)
        self.assertLess(len(fact.behavior), 120)
        self.assertNotIn("询问笔录", fact.behavior)
        self.assertEqual(fact.time, "2026年6月12日17时许")
        self.assertIn("新凯飞汽配", fact.location)
        self.assertIn("贺显作", fact.object)

    def test_text_agent_preserves_denial_facts_for_conflict_detection(self):
        content = (
            "询问笔录\n被询问人 李文杰\n"
            "问：你说一下事情经过？\n"
            "答：2026年6月12日17时许，在深圳市宝安区新凯飞汽配，我把贺显作的手机摔坏了。\n"
            "问：你与贺显作有没有打架？\n"
            "答：没有。\n"
            "问：现场有没有人受伤？\n"
            "答：贺显作眼角当时有肿包流血。"
        )

        facts = TextAgent().extract(Material("S-li", MaterialType.STATEMENT, content))

        self.assertTrue(any("没有打架" in fact.behavior for fact in facts))
        self.assertTrue(any(fact.object == "贺显作" for fact in facts if "没有打架" in fact.behavior))

    def test_text_agent_does_not_store_full_statement_as_behavior(self):
        content = (
            "询问笔录\n被询问人 贺显作\n"
            "问：你说一下自己的个人信息？\n"
            "答：我叫贺显作，男，44岁，现住深圳市宝安区。\n"
            "问：你说一下事情经过？\n"
            "答：2026年6月12日17时许，在深圳市宝安区新凯飞汽配，"
            "李文杰把我的手机摔在地上，导致屏幕损坏。\n"
            "问：你们双方有无动手？\n"
            "答：没有。\n"
            "问：你说的是否属实？\n"
            "答：属实。"
        )

        facts = TextAgent().extract(Material("S-he", MaterialType.STATEMENT, content))

        self.assertGreaterEqual(len(facts), 2)
        self.assertTrue(all(len(fact.behavior) < 120 for fact in facts))
        self.assertTrue(all("询问笔录" not in fact.behavior for fact in facts))
        self.assertTrue(any("手机" in fact.behavior and "摔" in fact.behavior for fact in facts))
        self.assertTrue(any("没有动手" in fact.behavior for fact in facts))

    def test_pic_agent_refines_vision_result_before_case_graph(self):
        class FakeVisionTool:
            def describe(self, material):
                return ImageEvidenceDescription(
                    pic="图片显示李文杰在车间将贺显作抱摔在地，旁边有工位和地面痕迹。",
                    text="监控截图 2026年6月12日17时许 新凯飞汽配",
                    confidence=0.94,
                )

        material = Material("P1", MaterialType.EVIDENCE_IMAGE, "待 Qwen 识别", "image.jpg")
        fact = PicAgent(vision_tool=FakeVisionTool()).extract(material)[0]

        self.assertIn("李文杰", fact.behavior)
        self.assertIn("抱摔", fact.behavior)
        self.assertLess(len(fact.behavior), 120)
        self.assertNotIn("图片内容：图片显示", fact.behavior)
        self.assertEqual(fact.time, "2026年6月12日17时许")
        self.assertIn("新凯飞汽配", fact.location)

    def test_report_agent_extracts_report_conclusion_without_full_text(self):
        content = (
            "司法鉴定意见书。被鉴定人：贺显作，男，44岁。"
            "资料摘要：双侧鼻骨、鼻中隔骨折。"
            "鉴定意见：被鉴定人贺显作所受的损伤为轻伤二级。"
            "2026年6月17日。司法鉴定人 曾拥军 郑杏斌。"
        )
        fact = ReportImageAgent().extract(Material("R1", MaterialType.REPORT_IMAGE, content))[0]

        self.assertEqual(fact.person, "贺显作")
        self.assertIn("轻伤二级", fact.behavior)
        self.assertLess(len(fact.behavior), 100)
        self.assertNotIn("司法鉴定人", fact.behavior)
        self.assertIn("双侧鼻骨", fact.object)

    def test_text_agent_summarizes_property_damage_instead_of_copying_event_answer(self):
        content = (
            "询问笔录\n被询问人 贺显作\n"
            "问：你说一下自己的个人信息？\n"
            "答：我叫贺显作，男，44岁，1982年2月18日出生。\n"
            "问：你说一下事情经过？\n"
            "答：2026年6月12日，在深圳市宝安区新凯飞汽配，我和同事李文杰在工作群里因为工作问题发生口角，"
            "之后他来我工位把我的手机摔在地上，导致屏幕损坏。随后他报警，警察到达现场将他带走。\n"
            "问：你们双方有无动手？\n"
            "答：没有。\n"
        )

        facts = TextAgent().extract(Material("S-he", MaterialType.STATEMENT, content))
        main_fact = facts[0]

        self.assertLess(len(main_fact.behavior), 60)
        self.assertEqual(main_fact.person, "贺显作")
        self.assertIn("李文杰", main_fact.behavior)
        self.assertIn("手机", main_fact.behavior)
        self.assertIn("损坏", main_fact.behavior)
        self.assertEqual(main_fact.object, "手机")
        self.assertEqual(main_fact.time, "2026年6月12日")
        self.assertIn("新凯飞汽配", main_fact.location)

    def test_text_agent_keeps_first_person_actor_for_property_damage(self):
        content = (
            "询问笔录\n被询问人 李文杰\n"
            "问：你说一下事情经过？\n"
            "答：2026年6月12日17时许，在深圳市宝安区新凯飞汽配，我和同事贺显作发生口角，"
            "他骂我，我就到他工位把他的手机摔坏了。之后我报警。\n"
        )

        fact = TextAgent().extract(Material("S-li", MaterialType.STATEMENT, content))[0]

        self.assertIn("李文杰", fact.behavior)
        self.assertNotIn("贺显作摔坏", fact.behavior)
        self.assertEqual(fact.object, "手机")

    def test_reasoning_uses_structured_fields_instead_of_full_copy(self):
        graph = CaseGraph(
            facts=[
                TextAgent().extract(
                    Material(
                        "S-li",
                        MaterialType.STATEMENT,
                        "被询问人 李文杰 问：你说一下事情经过？答：2026年6月12日17时许，在深圳市宝安区新凯飞汽配，李文杰抱摔贺显作致其受伤。",
                    )
                )[0]
            ]
        )
        report = ReasoningAgent().reason(
            {
                "confirmed_case_type": "故意伤害类案件",
                "evidence_graph": graph,
                "legal_matches": [],
                "conflicts": [],
            }
        )

        self.assertIn("时间地点", report)
        self.assertIn("行为事实", report)
        self.assertIn("2026年6月12日17时许", report)
        self.assertIn("深圳市宝安区新凯飞汽配", report)
        self.assertNotIn("问：你说一下事情经过", report)


if __name__ == "__main__":
    unittest.main()
