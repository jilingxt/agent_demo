import unittest

from case_agent_demo.evidence_reasoning import AssertionNormalizer
from case_agent_demo.models import CaseGraph, EvidenceNode


class AssertionNormalizerTests(unittest.TestCase):
    def test_metadata_rich_nodes_normalize_and_group_by_actor_predicate_target_and_event(self):
        graph = CaseGraph(
            nodes=[
                EvidenceNode(
                    node_id="N-support",
                    node_type="fact",
                    source_material_id="M-statement",
                    source_type="statement",
                    summary="witness describes the incident",
                    metadata={
                        "declarant": "witness-a",
                        "actor": "person-a",
                        "predicate": "violence",
                        "target_person": "person-b",
                        "object": "person-b",
                        "event_id": "event-1",
                        "stance": "affirm",
                        "modality": "observed",
                        "source_group": "witness-a-statement",
                        "origin_evidence": "statement-1",
                    },
                ),
                EvidenceNode(
                    node_id="N-deny",
                    node_type="fact",
                    source_material_id="M-denial",
                    source_type="statement",
                    summary="actor denies the incident",
                    metadata={
                        "declarant": "person-a",
                        "actor": "person-a",
                        "predicate": "violence",
                        "target_person": "person-b",
                        "object": "person-b",
                        "event_id": "event-1",
                        "stance": "deny",
                        "source_group": "person-a-statement",
                        "origin_evidence": "statement-2",
                    },
                ),
            ]
        )

        normalizer = AssertionNormalizer()
        assertions = normalizer.normalize_graph(graph)
        claims = normalizer.build_claims(assertions)

        self.assertEqual(assertions[0].actor, "person-a")
        self.assertEqual(assertions[0].predicate, "violence")
        self.assertEqual(assertions[0].stance, "affirm")
        self.assertEqual(assertions[0].source_group, "witness-a-statement")
        self.assertEqual(assertions[0].origin_evidence, "statement-1")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].subject, "person-a")
        self.assertEqual(claims[0].behavior_type, "violence")
        self.assertEqual(claims[0].target_person, "person-b")
        self.assertEqual(claims[0].event_id, "event-1")
        self.assertEqual(claims[0].supporting_node_ids, ["N-support"])
        self.assertEqual(claims[0].opposing_node_ids, ["N-deny"])

    def test_ambiguous_assertions_are_grouped_but_not_counted_as_support_or_opposition(self):
        graph = CaseGraph(
            nodes=[
                EvidenceNode(
                    node_id="N-memory-gap",
                    node_type="fact",
                    source_material_id="M-statement",
                    source_type="statement",
                    summary="witness cannot remember",
                    metadata={
                        "actor": "person-a",
                        "predicate": "violence",
                        "target_person": "person-b",
                        "event_id": "event-1",
                        "stance": "lack_of_memory",
                    },
                )
            ]
        )

        normalizer = AssertionNormalizer()
        assertions = normalizer.normalize_graph(graph)
        claims = normalizer.build_claims(assertions)

        self.assertEqual(assertions[0].stance, "ambiguous")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].ambiguous_node_ids, ["N-memory-gap"])
        self.assertEqual(claims[0].supporting_node_ids, [])
        self.assertEqual(claims[0].opposing_node_ids, [])


if __name__ == "__main__":
    unittest.main()
