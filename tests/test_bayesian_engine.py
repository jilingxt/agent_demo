import json
import unittest
from pathlib import Path

from case_agent_demo.bayesian_engine import BayesianInferenceEngine, ModelValidationError


MODEL_PATH = Path(__file__).parents[1] / "config" / "bayesian_models" / "intentional_injury_v1.json"


class BayesianInferenceEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = BayesianInferenceEngine(model_path=MODEL_PATH)

    def test_causation_rises_with_consistent_action_injury_mechanism_and_timing_evidence(self):
        baseline = self.engine.infer({})["node_values"]["causation"]
        supported = self.engine.infer(
            {
                "violent_action": 0.9,
                "injury_grade": 0.9,
                "mechanism_consistency": 0.9,
                "temporal_consistency": 0.9,
            }
        )["node_values"]["causation"]

        self.assertGreater(supported, baseline)

    def test_intentional_injury_model_exposes_the_full_claim_chain(self):
        values = self.engine.infer({})["node_values"]

        self.assertTrue(
            {
                "actor_present",
                "physical_contact",
                "violent_action",
                "injury_exists",
                "injury_grade",
                "mechanism_consistency",
                "temporal_consistency",
                "alternative_cause",
                "causation",
            }.issubset(values)
        )

    def test_causation_falls_when_alternative_cause_evidence_increases(self):
        supported = {
            "violent_action": 0.9,
            "injury_grade": 0.9,
            "mechanism_consistency": 0.9,
            "temporal_consistency": 0.9,
        }
        without_alternative = self.engine.infer(supported)["node_values"]["causation"]
        with_alternative = self.engine.infer({**supported, "alternative_cause": 0.9})["node_values"]["causation"]

        self.assertLess(with_alternative, without_alternative)

    def test_injury_evidence_does_not_upgrade_violent_action(self):
        baseline = self.engine.infer({})["node_values"]["violent_action"]
        injury_only = self.engine.infer({"injury_grade": 1.0})["node_values"]["violent_action"]

        self.assertEqual(injury_only, baseline)

    def test_invalid_models_and_cycles_are_rejected(self):
        duplicate_node = {
            "model_id": "duplicate",
            "version": "1",
            "calibration_status": "expert_prior",
            "nodes": [
                {"id": "same", "type": "prior", "prior": 0.1},
                {"id": "same", "type": "prior", "prior": 0.2},
            ],
        }
        invalid_parent = {
            "model_id": "invalid",
            "version": "1",
            "calibration_status": "expert_prior",
            "nodes": [{"id": "causation", "type": "logistic", "parents": ["missing"], "intercept": 0, "weights": {"missing": 1}}],
        }
        cyclic = {
            "model_id": "cyclic",
            "version": "1",
            "calibration_status": "expert_prior",
            "nodes": [
                {"id": "a", "type": "noisy_or", "parents": ["b"], "weights": {"b": 1}},
                {"id": "b", "type": "noisy_or", "parents": ["a"], "weights": {"a": 1}},
            ],
        }

        with self.assertRaises(ModelValidationError):
            BayesianInferenceEngine(model_spec=duplicate_node)
        with self.assertRaises(ModelValidationError):
            BayesianInferenceEngine(model_spec=invalid_parent)
        with self.assertRaises(ModelValidationError):
            BayesianInferenceEngine(model_spec=cyclic)

    def test_noisy_or_evaluates_parent_evidence(self):
        engine = BayesianInferenceEngine(
            model_spec={
                "model_id": "noisy-or",
                "version": "1",
                "calibration_status": "expert_prior",
                "nodes": [
                    {"id": "first", "type": "prior", "prior": 0.0},
                    {"id": "second", "type": "prior", "prior": 0.0},
                    {"id": "combined", "type": "noisy_or", "parents": ["first", "second"], "leak": 0.1, "weights": {"first": 0.5, "second": 0.8}},
                ],
            }
        )

        self.assertGreater(engine.infer({"first": 1.0, "second": 1.0})["node_values"]["combined"], 0.9)

    def test_parameter_hash_is_stable_and_auditable(self):
        first = self.engine.infer({})
        second = BayesianInferenceEngine(model_spec=json.loads(MODEL_PATH.read_text(encoding="utf-8"))).infer({})

        self.assertEqual(first["parameter_hash"], second["parameter_hash"])
        self.assertEqual(first["model_id"], "intentional_injury")
        self.assertEqual(first["version"], "1")
        self.assertEqual(first["calibration_status"], "expert_prior")

    def test_semantically_equivalent_specs_share_hash_and_node_values(self):
        ordered_spec = {
            "model_id": "semantic",
            "version": "1",
            "calibration_status": "expert_prior",
            "nodes": [
                {"id": "action", "type": "prior", "prior": 0.1},
                {"id": "injury", "type": "prior", "prior": 0.2},
                {"id": "timing", "type": "prior", "prior": 0.3},
                {
                    "id": "causation",
                    "type": "logistic",
                    "parents": ["action", "injury", "timing"],
                    "intercept": -0.4,
                    "weights": {"action": 0.3, "injury": 0.6, "timing": 0.9},
                },
            ],
        }
        reordered_spec = {
            "calibration_status": "expert_prior",
            "version": "1",
            "model_id": "semantic",
            "nodes": [
                {
                    "id": "causation",
                    "type": "logistic",
                    "parents": ["timing", "injury", "action"],
                    "intercept": -0.4,
                    "weights": {"timing": 0.9, "injury": 0.6, "action": 0.3},
                },
                {"id": "timing", "type": "prior", "prior": 0.3},
                {"id": "injury", "type": "prior", "prior": 0.2},
                {"id": "action", "type": "prior", "prior": 0.1},
            ],
        }

        ordered = BayesianInferenceEngine(model_spec=ordered_spec).infer({})
        reordered = BayesianInferenceEngine(model_spec=reordered_spec).infer({})

        self.assertEqual(ordered["parameter_hash"], reordered["parameter_hash"])
        self.assertEqual(ordered["node_values"], reordered["node_values"])

    def test_irrelevant_node_fields_are_rejected(self):
        prior_with_weights = {
            "model_id": "invalid",
            "version": "1",
            "calibration_status": "expert_prior",
            "nodes": [{"id": "action", "type": "prior", "prior": 0.2, "weights": {}}],
        }
        logistic_with_leak = {
            "model_id": "invalid",
            "version": "1",
            "calibration_status": "expert_prior",
            "nodes": [{"id": "action", "type": "logistic", "parents": [], "intercept": 0, "weights": {}, "leak": 0}],
        }

        with self.assertRaises(ModelValidationError):
            BayesianInferenceEngine(model_spec=prior_with_weights)
        with self.assertRaises(ModelValidationError):
            BayesianInferenceEngine(model_spec=logistic_with_leak)

    def test_child_before_parent_declaration_evaluates_topologically(self):
        engine = BayesianInferenceEngine(
            model_spec={
                "model_id": "declaration-order",
                "version": "1",
                "calibration_status": "expert_prior",
                "nodes": [
                    {"id": "child", "type": "logistic", "parents": ["parent"], "intercept": 0, "weights": {"parent": 2}},
                    {"id": "parent", "type": "prior", "prior": 0.75},
                ],
            }
        )

        self.assertAlmostEqual(engine.infer({})["node_values"]["child"], 1 / (1 + 2.718281828459045**-1.5))


if __name__ == "__main__":
    unittest.main()
