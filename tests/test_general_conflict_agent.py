import unittest

from case_agent_demo.agents import ConflictAgent, JudgeAgent, ReasoningAgent
from case_agent_demo.models import CaseGraph, Fact


class GeneralConflictAgentTests(unittest.TestCase):
    def test_detects_denied_violence_against_injury_report(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S-li", "statement", "李文杰", "李文杰称双方没有打架、没有动手", object="贺显作"),
                Fact(
                    "F2",
                    "R-injury",
                    "report_image",
                    "贺显作",
                    "法医鉴定报告认定贺显作所受损伤为轻伤二级、鼻骨骨折",
                    object="贺显作 轻伤二级、鼻骨骨折",
                ),
            ]
        )

        conflicts = ConflictAgent().detect(graph)

        self.assertTrue(any(item.conflict_type == "denial_vs_consequence" for item in conflicts))
        self.assertEqual(conflicts[0].severity, "high")
        self.assertIn("没有打架", conflicts[0].claim_a)
        self.assertIn("轻伤二级", conflicts[0].claim_b)

    def test_detects_denied_taking_against_property_taken(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "张三", "张三称没有拿手机", object="手机"),
                Fact("F2", "P1", "evidence_image", "张三", "监控显示张三拿走手机", object="手机"),
            ]
        )

        conflicts = ConflictAgent().detect(graph)

        self.assertTrue(any(item.conflict_type == "direct_fact_contradiction" for item in conflicts))
        self.assertTrue(any("手机" in item.claim_a + item.claim_b for item in conflicts))

    def test_detects_denied_property_damage_against_damaged_object(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "王五", "王五称没有损坏门锁", object="门锁"),
                Fact("F2", "P1", "evidence_image", "未识别人员", "现场照片显示门锁损坏", object="门锁"),
            ]
        )

        conflicts = ConflictAgent().detect(graph)

        self.assertTrue(any(item.conflict_type == "direct_fact_contradiction" for item in conflicts))
        self.assertTrue(any("门锁" in item.claim_a + item.claim_b for item in conflicts))

    def test_judge_and_reasoning_surface_general_high_conflict(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S-li", "statement", "李文杰", "李文杰称双方没有打架", object="贺显作"),
                Fact("F2", "R-injury", "report_image", "贺显作", "鉴定意见显示贺显作轻伤二级", object="贺显作 轻伤二级"),
            ]
        )
        conflicts = ConflictAgent().detect(graph)
        report = ReasoningAgent().reason(
            {
                "confirmed_case_type": "故意伤害类案件",
                "evidence_graph": graph,
                "legal_matches": [],
                "conflicts": conflicts,
            }
        )
        challenges = JudgeAgent().challenge({"draft_report": report, "conflicts": conflicts, "legal_matches": ["L1"]})

        self.assertIn("denial_vs_consequence", report)
        self.assertTrue(any(item.challenge_type == "unresolved_conflict" for item in challenges))


if __name__ == "__main__":
    unittest.main()
