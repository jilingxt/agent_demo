import unittest

from case_agent_demo.evidence_reasoning import AssertionNormalizer
from case_agent_demo.models import CaseGraph, EvidenceNode


class AssertionNormalizerTests(unittest.TestCase):
    def test_target_person_and_legacy_object_share_one_claim_and_id(self):
        graph = CaseGraph(
            nodes=[
                EvidenceNode(
                    node_id="N-target",
                    node_type="fact",
                    source_material_id="M-target",
                    source_type="statement",
                    summary="first account",
                    metadata={
                        "actor": "person-a",
                        "predicate": "violence",
                        "target_person": "person-b",
                        "event_id": "event-1",
                    },
                ),
                EvidenceNode(
                    node_id="N-object",
                    node_type="fact",
                    source_material_id="M-object",
                    source_type="statement",
                    summary="second account",
                    metadata={
                        "actor": "person-a",
                        "predicate": "violence",
                        "object": "person-b",
                        "event_id": "event-1",
                    },
                ),
            ]
        )

        claims = AssertionNormalizer().build_claims(AssertionNormalizer().normalize_graph(graph))

        self.assertEqual(len(claims), 1)
        self.assertEqual(len({claim.claim_id for claim in claims}), 1)
        self.assertEqual(claims[0].supporting_node_ids, ["N-target", "N-object"])

    def test_equivalent_target_claim_fields_are_order_independent(self):
        target_node = EvidenceNode(
            node_id="N-target",
            node_type="fact",
            source_material_id="M-target",
            source_type="statement",
            summary="target account",
            metadata={
                "actor": "person-a",
                "predicate": "violence",
                "target_person": "person-b",
                "event_id": "event-1",
            },
        )
        object_node = EvidenceNode(
            node_id="N-object",
            node_type="fact",
            source_material_id="M-object",
            source_type="statement",
            summary="object account",
            metadata={
                "actor": "person-a",
                "predicate": "violence",
                "object": "person-b",
                "event_id": "event-1",
            },
        )
        normalizer = AssertionNormalizer()

        forward = normalizer.build_claims(normalizer.normalize_graph(CaseGraph(nodes=[target_node, object_node])))[0]
        reversed_claim = normalizer.build_claims(normalizer.normalize_graph(CaseGraph(nodes=[object_node, target_node])))[0]

        self.assertEqual(reversed_claim.claim_id, forward.claim_id)
        self.assertEqual(reversed_claim.target_person, forward.target_person)
        self.assertEqual(reversed_claim.object, forward.object)
        self.assertEqual(reversed_claim.target_person, "person-b")
        self.assertEqual(reversed_claim.object, "person-b")

    def test_metadata_sparse_node_uses_existing_claim_type_inference(self):
        node = EvidenceNode(
            node_id="N-fallback",
            node_type="fact",
            source_material_id="M-fallback",
            source_type="statement",
            summary="person-a fought person-b",
            behavior="打架",
            object="person-b",
        )

        assertion = AssertionNormalizer().normalize_graph(CaseGraph(nodes=[node]))[0]

        self.assertEqual(assertion.predicate, "violence")

    def test_property_support_claims_keep_different_objects_separate(self):
        nodes = [
            EvidenceNode(
                node_id=f"N-{obj}",
                node_type="fact",
                source_material_id=f"M-{obj}",
                source_type="statement",
                summary=f"{obj}原先占有",
                metadata={
                    "actor": "张三",
                    "predicate": "prior_possession",
                    "object": obj,
                    "event_id": "event-1",
                },
            )
            for obj in ("手机", "现金")
        ]

        claims = AssertionNormalizer().build_claims(
            AssertionNormalizer().normalize_graph(CaseGraph(nodes=nodes))
        )

        self.assertEqual({claim.object for claim in claims}, {"手机", "现金"})
        self.assertEqual(len(claims), 2)

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
