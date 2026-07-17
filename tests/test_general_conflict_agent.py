import unittest

from case_agent_demo.agents import ConflictAgent, JudgeAgent, ReasoningAgent
from case_agent_demo.models import CaseGraph, Fact


class GeneralConflictAgentTests(unittest.TestCase):
    def test_different_predicates_do_not_form_a_direct_conflict(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S-li", "statement", "李文杰", "行为否认", object="贺显作", metadata={"assertions": [{"actor": "李文杰", "target_person": "贺显作", "predicate": "violence", "stance": "deny"}]}),
                Fact(
                    "F2",
                    "R-injury",
                    "report_image",
                    "贺显作",
                    "法医鉴定报告认定贺显作所受损伤为轻伤二级、鼻骨骨折",
                    object="贺显作 轻伤二级、鼻骨骨折", metadata={"assertions": [{"actor": "贺显作", "target_person": "贺显作", "predicate": "injury_grade", "stance": "affirm"}]},
                ),
            ]
        )

        conflicts = ConflictAgent().detect(graph)

        self.assertEqual(conflicts, [])

    def test_detects_denied_taking_against_property_taken(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "张三", "否认拿取", object="手机", metadata={"assertions": [{"actor": "张三", "object": "手机", "predicate": "taking_property", "stance": "deny"}]}),
                Fact("F2", "P1", "evidence_image", "张三", "记录拿取", object="手机", metadata={"assertions": [{"actor": "张三", "object": "手机", "predicate": "taking_property", "stance": "affirm"}]}),
            ]
        )

        conflicts = ConflictAgent().detect(graph)

        self.assertTrue(any(item.conflict_type == "direct_fact_contradiction" for item in conflicts))

    def test_detects_denied_property_damage_against_damaged_object(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "王五", "否认损坏", object="门锁", metadata={"assertions": [{"actor": "王五", "object": "门锁", "predicate": "property_damage", "stance": "deny"}]}),
                Fact("F2", "P1", "evidence_image", "王五", "记录损坏", object="门锁", metadata={"assertions": [{"actor": "王五", "object": "门锁", "predicate": "property_damage", "stance": "affirm"}]}),
            ]
        )

        conflicts = ConflictAgent().detect(graph)

        self.assertTrue(any(item.conflict_type == "direct_fact_contradiction" for item in conflicts))

    def test_judge_and_reasoning_surface_general_high_conflict(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S-li", "statement", "李文杰", "否认行为", object="贺显作", metadata={"assertions": [{"actor": "李文杰", "target_person": "贺显作", "predicate": "violence", "stance": "deny"}]}),
                Fact("F2", "R-video", "report_image", "李文杰", "记录行为", object="贺显作", metadata={"assertions": [{"actor": "李文杰", "target_person": "贺显作", "predicate": "violence", "stance": "affirm"}]}),
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

        self.assertIn("direct_fact_contradiction", report)
        self.assertTrue(any(item.challenge_type == "unresolved_conflict" for item in challenges))


if __name__ == "__main__":
    unittest.main()
