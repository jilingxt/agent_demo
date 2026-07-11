import unittest
from pathlib import Path

from case_agent_demo.confidence import ConfidenceEngine, LEGACY_LABELS
from case_agent_demo.evidence_reasoning import AuthorityValidator, SubjectiveEvidenceEngine
from case_agent_demo.models import CaseGraph, EvidenceAssertion, EvidenceClaim, EvidenceNode


VERIFIED_FORENSIC_METADATA = {
    "authority": {
        "issuer": "qualified_forensic_institution",
        "document_type": "forensic_injury_grade_report",
        "competence_verified": True,
        "authenticity_verified": True,
        "procedure_verified": True,
        "subject_identity_verified": True,
        "method_verified": True,
        "standard_verified": True,
        "scope_verified": True,
        "human_verified": True,
    }
}


def forensic_assertion(assertion_id="A-forensic", stance="affirm", **metadata):
    return EvidenceAssertion(
        assertion_id=assertion_id,
        node_id=assertion_id,
        predicate="injury_grade",
        stance=stance,
        source_group=assertion_id,
        origin_evidence=assertion_id,
        metadata={**VERIFIED_FORENSIC_METADATA, **metadata},
    )


class AuthorityReasoningTests(unittest.TestCase):
    def setUp(self):
        self.engine = SubjectiveEvidenceEngine()
        self.injury_grade_claim = EvidenceClaim("CL-injury-grade", "victim-a", "injury_grade")

    def test_verified_forensic_injury_grade_anchor_is_limited_to_injury_predicates(self):
        assertion = forensic_assertion()

        assessment = AuthorityValidator().validate(assertion)
        injury_assessment = self.engine.evaluate(self.injury_grade_claim, [assertion])

        self.assertEqual(assessment.status, "authority_valid")
        self.assertEqual(assessment.mean, 0.99)
        self.assertEqual(assessment.strength, 50.0)
        self.assertEqual(injury_assessment.status, "authority_anchored")
        self.assertGreater(injury_assessment.opinion.support, 0.94)
        for predicate in ("violence", "actor_identity", "intent", "causation", "criminal_liability"):
            claim = EvidenceClaim(f"CL-{predicate}", "victim-a", predicate)
            result = self.engine.evaluate(claim, [assertion])
            self.assertEqual(result.opinion.support, 0.0)
            self.assertNotEqual(result.status, "authority_anchored")

    def test_ordinary_denial_does_not_materially_defeat_valid_injury_grade_anchor(self):
        anchor = forensic_assertion()
        denial = EvidenceAssertion(
            assertion_id="A-denial",
            node_id="A-denial",
            predicate="injury_grade",
            stance="deny",
            source_group="ordinary-denial",
            origin_evidence="ordinary-denial",
        )

        assessment = self.engine.evaluate(self.injury_grade_claim, [anchor, denial])

        self.assertEqual(assessment.status, "authority_anchored")
        self.assertGreater(assessment.opinion.support, 0.90)
        self.assertLess(assessment.opinion.conflict, 0.10)

    def test_conflicting_authoritative_reappraisal_contests_injury_grade_anchor(self):
        anchor = forensic_assertion()
        reappraisal = forensic_assertion(
            "A-reappraisal",
            stance="deny",
            authority={
                **VERIFIED_FORENSIC_METADATA["authority"],
                "document_type": "forensic_injury_reappraisal",
                "defeater": True,
            },
        )

        assessment = self.engine.evaluate(self.injury_grade_claim, [anchor, reappraisal])

        self.assertEqual(assessment.status, "authority_contested")
        self.assertGreater(assessment.opinion.conflict, 0.90)

    def test_official_name_without_explicit_verification_stays_unverified(self):
        assertion = EvidenceAssertion(
            assertion_id="A-unverified",
            node_id="A-unverified",
            predicate="injury_grade",
            stance="affirm",
            source_group="official",
            origin_evidence="official",
            metadata={"source_type": "forensic_report", "source_party": "official"},
        )

        authority = AuthorityValidator().validate(assertion)
        assessment = self.engine.evaluate(self.injury_grade_claim, [assertion])

        self.assertEqual(authority.status, "unverified")
        self.assertNotEqual(assessment.status, "authority_anchored")
        self.assertLess(assessment.opinion.support, 0.50)

    def test_ordinary_assertion_from_a_different_claim_does_not_add_support(self):
        injury_assertion = EvidenceAssertion(
            assertion_id="A-ordinary-injury",
            node_id="A-ordinary-injury",
            actor="actor-a",
            predicate="injury_grade",
            target_person="victim-a",
            event_id="event-a",
            stance="affirm",
            source_group="ordinary-injury",
            origin_evidence="ordinary-injury",
        )
        violence_claim = EvidenceClaim(
            "CL-violence",
            "actor-a",
            "violence",
            target_person="victim-a",
            event_id="event-a",
        )

        assessment = self.engine.evaluate(violence_claim, [injury_assertion])

        self.assertEqual(assessment.opinion.support, 0.0)
        self.assertEqual(assessment.status, "unassessed")

    def test_scoped_ordinary_assertion_requires_the_claim_target(self):
        assertion = EvidenceAssertion(
            assertion_id="A-missing-target",
            node_id="A-missing-target",
            actor="actor-a",
            predicate="violence",
            event_id="event-a",
            stance="affirm",
            source_group="missing-target",
            origin_evidence="missing-target",
        )
        claim = EvidenceClaim(
            "CL-targeted-violence",
            "actor-a",
            "violence",
            target_person="victim-a",
            event_id="event-a",
        )

        assessment = self.engine.evaluate(claim, [assertion])

        self.assertEqual(assessment.opinion.support, 0.0)

    def test_missing_external_rules_path_uses_conservative_default_rules(self):
        missing_path = Path(__file__).with_name("missing_authority_rules.json")

        assessment = AuthorityValidator(missing_path).validate(forensic_assertion())

        self.assertEqual(assessment.status, "authority_valid")
        self.assertEqual(assessment.mean, 0.99)
        self.assertEqual(assessment.strength, 50.0)

    def test_confidence_engine_maps_authority_statuses_to_legacy_labels(self):
        anchored = ConfidenceEngine().score_claims(CaseGraph(nodes=[self._forensic_node("N-anchor")]))[0]
        contested = ConfidenceEngine().score_claims(
            CaseGraph(
                nodes=[
                    self._forensic_node("N-anchor"),
                    self._forensic_node("N-reappraisal", stance="deny", defeater=True),
                ]
            )
        )[0]

        self.assertEqual(anchored.confidence_profile.label, LEGACY_LABELS["supported"])
        self.assertGreater(anchored.confidence_profile.final_score, 0.90)
        self.assertEqual(contested.confidence_profile.label, LEGACY_LABELS["contested"])
        self.assertTrue(any("authoritative defeater" in reason for reason in contested.confidence_profile.reasons))

    @staticmethod
    def _forensic_node(node_id, stance="affirm", defeater=False):
        return EvidenceNode(
            node_id=node_id,
            node_type="fact",
            source_material_id=node_id,
            source_type="forensic_report",
            summary="forensic injury grade",
            metadata={
                "actor": "actor-a",
                "predicate": "injury_grade",
                "target_person": "victim-a",
                "event_id": "event-a",
                "stance": stance,
                "source_group": node_id,
                "origin_evidence": node_id,
                "authority": {
                    **VERIFIED_FORENSIC_METADATA["authority"],
                    "document_type": "forensic_injury_reappraisal" if defeater else "forensic_injury_grade_report",
                    "defeater": defeater,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
