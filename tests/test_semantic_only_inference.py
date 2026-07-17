import unittest

from case_agent_demo.agents import ConflictAgent, PicAgent, PlanningAgent, ReportImageAgent, TextAgent
from case_agent_demo.domain_affinity import CaseDomainRouter
from case_agent_demo.evidence_reasoning import AssertionNormalizer
from case_agent_demo.models import (
    CaseGraph,
    EvidenceClaim,
    EvidenceNode,
    Fact,
    Material,
    MaterialType,
)
from case_agent_demo.relation_tools import RelationRuleTool
from case_agent_demo.workflow import CaseWorkflow


class StructuredRuntime:
    def __init__(self, payload):
        self.payload = payload

    def run_json(self, prompt_name, profile, user_input, fallback, parser):
        del prompt_name, profile, user_input, fallback
        return parser(self.payload)


class SemanticOnlyInferenceTests(unittest.TestCase):
    def test_text_without_semantic_runtime_abstains_instead_of_matching_keywords(self):
        fact = TextAgent().extract(
            Material("S1", MaterialType.STATEMENT, "陈述中出现轻伤、骨折和没有受伤等词语。")
        )[0]

        self.assertEqual(fact.metadata["semantic_status"], "unresolved")
        self.assertEqual(fact.metadata["predicate"], "unresolved_observation")
        self.assertEqual(fact.metadata["stance"], "ambiguous")

    def test_text_accepts_open_predicate_and_semantic_stance_from_agent(self):
        runtime = StructuredRuntime(
            {
                "facts": [
                    {
                        "person": "陈述人甲",
                        "declarant": "陈述人甲",
                        "actor": "相关人员乙",
                        "target_person": "陈述人甲",
                        "object": "相关对象丙",
                        "predicate": "custom_contact_event",
                        "stance": "deny",
                        "behavior": "相关人员乙否认发生该接触事件",
                        "evidence_span": "原文中的对应句段",
                        "confidence": 0.81,
                    }
                ]
            }
        )

        fact = TextAgent(runtime=runtime).extract(
            Material("S1", MaterialType.STATEMENT, "使用任何未被词表枚举的自然语言。")
        )[0]

        assertion = fact.metadata["assertions"][0]
        self.assertEqual(assertion["predicate"], "custom_contact_event")
        self.assertEqual(assertion["stance"], "deny")
        self.assertEqual(assertion["evidence_span"], "原文中的对应句段")
        self.assertEqual(assertion["object"], "相关对象丙")

    def test_nested_assertions_cannot_override_validated_top_level_semantics(self):
        runtime = StructuredRuntime(
            {
                "facts": [
                    {
                        "predicate": "custom_event",
                        "stance": "affirm",
                        "behavior": "结构化事实",
                        "metadata": {
                            "assertions": [
                                {
                                    "predicate": "keyword_guessed_event",
                                    "stance": "invalid_stance",
                                }
                            ]
                        },
                    }
                ]
            }
        )

        fact = TextAgent(runtime=runtime).extract(
            Material("S1", MaterialType.STATEMENT, "任意原文")
        )[0]

        self.assertEqual(fact.metadata["assertions"][0]["predicate"], "custom_event")
        self.assertEqual(fact.metadata["assertions"][0]["stance"], "affirm")

    def test_image_and_report_without_semantic_runtime_are_unresolved(self):
        image = PicAgent().extract(
            Material("P1", MaterialType.EVIDENCE_IMAGE, "人工提供的图片观察文本")
        )[0]
        report = ReportImageAgent().extract(
            Material("R1", MaterialType.REPORT_IMAGE, "人工提供的报告文本")
        )[0]

        self.assertEqual(image.metadata["semantic_status"], "unresolved")
        self.assertEqual(report.metadata["semantic_status"], "unresolved")

    def test_normalizer_does_not_infer_predicate_or_stance_from_raw_words(self):
        graph = CaseGraph(
            nodes=[
                EvidenceNode(
                    "F1",
                    "fact",
                    "S1",
                    "statement",
                    "没有受伤但未排除其他结果",
                    behavior="没有受伤但未排除其他结果",
                    metadata={},
                )
            ]
        )

        assertion = AssertionNormalizer().normalize_graph(graph)[0]

        self.assertEqual(assertion.predicate, "unresolved_observation")
        self.assertEqual(assertion.stance, "ambiguous")

    def test_relation_rules_use_structured_polarity_not_negative_words(self):
        affirmative = EvidenceNode(
            "F1",
            "fact",
            "S1",
            "statement",
            "文本里出现没有和否认",
            object="某对象",
            polarity="affirm",
            claim_type="custom_event",
        )
        corroborating = EvidenceNode(
            "F2",
            "fact",
            "S2",
            "statement",
            "另一份记录",
            object="某对象",
            polarity="affirm",
            claim_type="custom_event",
        )
        denying = EvidenceNode(
            "F3",
            "fact",
            "S3",
            "statement",
            "没有使用任何否定词",
            object="某对象",
            polarity="deny",
            claim_type="custom_event",
        )

        tool = RelationRuleTool()

        self.assertFalse(
            any(edge.edge_type == "contradicts" for edge in tool._pair_edges(affirmative, corroborating))
        )
        self.assertTrue(
            any(edge.edge_type == "contradicts" for edge in tool._pair_edges(affirmative, denying))
        )

    def test_conflict_agent_ignores_unstructured_keyword_only_facts(self):
        graph = CaseGraph(
            facts=[
                Fact("F1", "S1", "statement", "人员甲", "人员甲称没有造成轻伤", object="人员乙"),
                Fact("F2", "S2", "statement", "人员乙", "材料记载人员乙存在轻伤", object="人员乙"),
            ]
        )

        self.assertEqual(ConflictAgent().detect(graph), [])

    def test_domain_router_uses_registered_predicates_not_raw_keywords(self):
        graph = CaseGraph(
            nodes=[
                EvidenceNode(
                    "F1",
                    "fact",
                    "S1",
                    "statement",
                    "轻伤、重伤、骨折只是未解析原文",
                    claim_type="unresolved_observation",
                )
            ],
            claims=[EvidenceClaim("C1", "人员甲", "injury_exists")],
        )

        domains = CaseDomainRouter().infer_domains("", graph)

        self.assertTrue(any(item.domain_id == "personal_rights" for item in domains))

        unresolved_graph = CaseGraph(nodes=graph.nodes, claims=[])
        self.assertEqual(CaseDomainRouter().infer_domains("", unresolved_graph), [])

    def test_planning_without_semantic_runtime_returns_unknown(self):
        suggestion = PlanningAgent().suggest(
            [Material("S1", MaterialType.STATEMENT, "轻伤、转账、损坏等未解析原文")]
        )

        self.assertEqual(suggestion.suggested_case_types[0]["domain_id"], "unknown")
        self.assertEqual(suggestion.suggested_case_types[0]["confidence"], 0.0)

    def test_workflow_attaches_one_semantic_runtime_to_all_understanding_agents(self):
        client = object()
        workflow = CaseWorkflow()

        workflow.attach_semantic_runtime(client)

        self.assertIs(workflow.planning_agent.runtime.client, client)
        self.assertIs(workflow.text_agent.runtime.client, client)
        self.assertIs(workflow.pic_agent.runtime.client, client)
        self.assertIs(workflow.report_image_agent.runtime.client, client)
        self.assertIs(workflow.reasoning_agent.runtime.client, client)


if __name__ == "__main__":
    unittest.main()
