import json
from pathlib import Path

from case_agent_demo.bayesian_engine import BayesianInferenceEngine
from case_agent_demo.bayesian_tool import BayesianModelRegistry


ROOT = Path(__file__).parents[1]
REGISTRY_PATH = ROOT / "config" / "bayesian_models" / "registry.json"
ELEMENTS_PATH = ROOT / "config" / "legal_elements" / "case_family_elements.json"


def test_registry_contains_equal_priority_peer_families():
    registry = BayesianModelRegistry(REGISTRY_PATH)

    assert [model.model_id for model in registry.models] == [
        "conduct_result",
        "property_taking",
        "public_order",
        "public_safety",
        "status_duty",
        "deception_disposition",
    ]
    assert {model.priority for model in registry.models} == {0}
    assert all("intentional_injury" not in model.model_id for model in registry.models)


def test_every_registered_model_loads_and_declares_only_factual_outputs():
    registry = BayesianModelRegistry(REGISTRY_PATH)
    forbidden = {
        "guilt",
        "criminal_liability",
        "punishment",
        "legal_applicability",
        "qualified_actor",
        "duty_exists",
        "authorization_absent",
        "prohibited_conduct",
        "duty_violation_supported",
    }

    for registered in registry.models:
        result = BayesianInferenceEngine(registered.path).infer({})
        assert result["model_id"] == registered.model_id
        assert set(registered.derived_nodes).isdisjoint(forbidden)
        assert set(result["node_values"]).isdisjoint(forbidden)
        assert set(registered.derived_nodes).issubset(result["node_values"])


def test_conduct_result_model_respects_support_and_alternative_cause():
    engine = BayesianInferenceEngine(
        ROOT / "config" / "bayesian_models" / "conduct_result_v1.json"
    )
    supported = {
        "conduct": 0.9,
        "result_exists": 0.9,
        "mechanism_consistency": 0.9,
        "temporal_consistency": 0.9,
        "alternative_cause": 0.05,
    }

    high = engine.infer(supported)["node_values"]["causation"]
    low = engine.infer({**supported, "alternative_cause": 0.95})["node_values"]["causation"]

    assert high > 0.7
    assert low < high


def test_property_taking_model_uses_possession_transfer_not_legal_conclusion():
    engine = BayesianInferenceEngine(
        ROOT / "config" / "bayesian_models" / "property_taking_v1.json"
    )
    weak = engine.infer({})["node_values"]["taking_supported"]
    strong = engine.infer(
        {
            "prior_possession": 0.9,
            "taking_action": 0.9,
            "possession_transfer": 0.9,
            "property_trace": 0.8,
            "alternative_explanation": 0.05,
        }
    )["node_values"]["taking_supported"]

    assert strong > weak
    assert strong > 0.7


def test_public_order_public_safety_and_status_models_move_with_evidence():
    scenarios = [
        (
            "public_order_v1.json",
            "order_disruption",
            {
                "conduct": 0.9,
                "public_context": 0.9,
                "operational_impact": 0.9,
                "persistence_or_group": 0.8,
            },
        ),
        (
            "public_safety_v1.json",
            "public_danger",
            {
                "hazardous_conduct": 0.9,
                "dangerous_object_or_condition": 0.9,
                "exposure": 0.9,
                "control_failure": 0.8,
            },
        ),
        (
            "status_duty_v1.json",
            "status_duty_facts_supported",
            {
                "qualification_record_present": 0.9,
                "duty_record_present": 0.9,
                "conduct_recorded": 0.9,
                "authorization_record_absent": 0.9,
            },
        ),
    ]

    for file_name, output, evidence in scenarios:
        engine = BayesianInferenceEngine(ROOT / "config" / "bayesian_models" / file_name)
        assert engine.infer(evidence)["node_values"][output] > engine.infer({})["node_values"][output]


def test_legal_element_taxonomy_covers_indexed_laws_and_separates_normative_rules():
    data = json.loads(ELEMENTS_PATH.read_text(encoding="utf-8"))

    assert set(data["source_laws"]) == {
        "中华人民共和国刑法（2023年修正）",
        "中华人民共和国治安管理处罚法（2025年修订）",
        "中华人民共和国刑事诉讼法（2018年修正）",
    }
    assert {item["family_id"] for item in data["case_families"]} == {
        "conduct_result",
        "property_taking",
        "public_order",
        "public_safety",
        "status_duty",
        "deception_disposition",
    }
    assert {
        "age_threshold",
        "amount_threshold",
        "frequency_threshold",
        "legal_defense",
        "administrative_criminal_boundary",
    }.issubset(data["deterministic_legal_elements"])
