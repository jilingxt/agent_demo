import math
import unittest

from case_agent_demo.confidence import ConfidenceEngine
from case_agent_demo.evidence_reasoning import EvidenceQualityEvaluator, SubjectiveEvidenceEngine
from case_agent_demo.models import CaseGraph, EvidenceAssertion, EvidenceClaim, EvidenceNode


QUALITY_VALUES = {
    "extraction_quality": 1.0,
    "relevance": 1.0,
    "specificity": 1.0,
    "directness": 1.0,
    "authenticity": 1.0,
    "procedural_integrity": 1.0,
    "internal_consistency": 1.0,
    "verifiability": 1.0,
}


def assertion(assertion_id, stance="affirm", source_group="group-1", origin="origin-1", **quality):
    return EvidenceAssertion(
        assertion_id=assertion_id,
        node_id=assertion_id,
        stance=stance,
        source_group=source_group,
        origin_evidence=origin,
        metadata={**QUALITY_VALUES, **quality},
    )


class SubjectiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.claim = EvidenceClaim("CL-1", "person-a", "violence")
        self.engine = SubjectiveEvidenceEngine()

    def test_quality_is_weighted_geometric_mean(self):
        evidence = assertion("A-1", directness=0.25)

        quality = EvidenceQualityEvaluator().evaluate(evidence, self.claim)

        self.assertAlmostEqual(quality, 0.25**0.15)

    def test_no_evidence_is_fully_uncertain(self):
        assessment = self.engine.evaluate(self.claim, [])

        self.assertEqual(assessment.opinion.support, 0.0)
        self.assertEqual(assessment.opinion.opposition, 0.0)
        self.assertEqual(assessment.opinion.uncertainty, 1.0)
        self.assertEqual(assessment.status, "unassessed")

    def test_independent_supporting_groups_add_evidence(self):
        one_group = self.engine.evaluate(self.claim, [assertion("A-1")])
        two_groups = self.engine.evaluate(
            self.claim,
            [assertion("A-1"), assertion("A-2", source_group="group-2", origin="origin-2")],
        )

        self.assertGreater(two_groups.opinion.support, one_group.opinion.support)
        self.assertLess(two_groups.opinion.uncertainty, one_group.opinion.uncertainty)

    def test_duplicate_origins_contribute_only_the_strongest_support(self):
        duplicate = self.engine.evaluate(
            self.claim,
            [
                assertion("A-low", source_group="group-1", origin="origin-1", directness=0.1),
                assertion("A-high", source_group="group-2", origin="origin-1", directness=0.9),
            ],
        )
        strongest = self.engine.evaluate(
            self.claim,
            [assertion("A-high", source_group="group-2", origin="origin-1", directness=0.9)],
        )

        self.assertAlmostEqual(duplicate.opinion.support, strongest.opinion.support)

    def test_direct_denial_adds_disbelief_without_zeroing_belief(self):
        assessment = self.engine.evaluate(
            self.claim,
            [assertion("A-support"), assertion("A-denial", stance="deny", source_group="group-2", origin="origin-2")],
        )

        self.assertGreater(assessment.opinion.support, 0.0)
        self.assertGreater(assessment.opinion.opposition, 0.0)

    def test_lack_of_memory_and_uncertain_assertions_are_neutral(self):
        assessment = self.engine.evaluate(
            self.claim,
            [assertion("A-memory", stance="lack_of_memory"), assertion("A-uncertain", stance="uncertain")],
        )

        self.assertEqual(assessment.opinion.support, 0.0)
        self.assertEqual(assessment.opinion.opposition, 0.0)
        self.assertEqual(assessment.opinion.uncertainty, 1.0)

    def test_confidence_facade_does_not_use_source_party_as_truth_weight(self):
        def score(source_party):
            graph = CaseGraph(
                nodes=[
                    EvidenceNode(
                        node_id="N-1",
                        node_type="fact",
                        source_material_id="M-1",
                        source_type="statement",
                        summary="account",
                        source_party=source_party,
                        metadata={
                            "actor": "person-a",
                            "predicate": "violence",
                            "event_id": "event-1",
                            "source_group": "group-1",
                            "origin_evidence": "origin-1",
                            **QUALITY_VALUES,
                        },
                    )
                ]
            )
            return ConfidenceEngine().score_claims(graph)[0].confidence_profile.final_score

        self.assertEqual(score("suspect"), score("victim"))
        self.assertEqual(score("victim"), score("official"))


if __name__ == "__main__":
    unittest.main()
