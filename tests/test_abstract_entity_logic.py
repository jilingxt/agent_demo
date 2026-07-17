import unittest
from pathlib import Path

from case_agent_demo.agents import (
    ConflictAgent,
    PlanningAgent,
)
from case_agent_demo.models import CaseGraph, Fact, Material, MaterialType
from plugins.reasoning_visualizer.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


class AbstractEntityLogicTests(unittest.TestCase):
    def test_conflict_target_comes_from_structured_assertions(self):
        graph = CaseGraph(
            facts=[
                Fact(
                    "F1",
                    "S1",
                    "statement",
                    "周海",
                    "周海明确否认实施损坏行为",
                    metadata={
                        "assertions": [
                            {
                                "actor": "周海",
                                "predicate": "property_damage",
                                "stance": "deny",
                                "object": "涉案设备",
                            }
                        ]
                    },
                ),
                Fact(
                    "F2",
                    "R1",
                    "report_image",
                    "记录人员",
                    "检测记录显示存在损坏结果",
                    metadata={
                        "assertions": [
                            {
                                "actor": "周海",
                                "predicate": "property_damage",
                                "stance": "affirm",
                                "object": "涉案设备",
                            }
                        ]
                    },
                ),
            ]
        )

        conflicts = ConflictAgent().detect(graph)

        self.assertTrue(
            any(item.conflict_type == "direct_fact_contradiction" for item in conflicts)
        )

    def test_planning_without_semantic_runtime_abstains(self):
        suggestion = PlanningAgent().suggest(
            [
                Material(
                    "S1",
                    MaterialType.STATEMENT,
                    "陈述人称对方虚构交易事项，使其产生错误认识后转账。",
                )
            ]
        )

        self.assertEqual(
            suggestion.suggested_case_types[0]["domain_id"],
            "unknown",
        )
        self.assertTrue(suggestion.requires_human_confirmation)

    def test_same_actor_does_not_make_different_objects_conflict(self):
        def fact(fact_id: str, stance: str, obj: str) -> Fact:
            return Fact(
                fact_id,
                fact_id,
                "statement",
                "周海",
                f"关于{obj}的陈述",
                metadata={
                    "assertions": [
                        {
                            "actor": "周海",
                            "predicate": "property_damage",
                            "stance": stance,
                            "object": obj,
                        }
                    ]
                },
            )

        conflicts = ConflictAgent().detect(
            CaseGraph(facts=[fact("F1", "deny", "仓库门"), fact("F2", "affirm", "运输箱")])
        )

        self.assertEqual(conflicts, [])

    def test_runtime_prompts_do_not_embed_legacy_case_entities(self):
        targets = (
            ROOT / "case_agent_demo" / "agents.py",
            ROOT / "config" / "prompts" / "text_agent.md",
            ROOT / "config" / "prompts" / "report_image_agent.md",
        )
        forbidden = ("贺显作", "李文杰", "新凯飞汽配", "石岩派出所")

        for target in targets:
            content = target.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, content, f"{value} remains in {target}")

    def test_visualizer_requires_an_explicit_input_source(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
