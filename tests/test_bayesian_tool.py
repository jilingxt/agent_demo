import json

import pytest

from case_agent_demo.bayesian_engine import ModelValidationError
from case_agent_demo.bayesian_tool import BayesianEvidenceTool, BayesianModelRegistry
from case_agent_demo.models import ClaimAssessment, ClaimOpinion, EvidenceClaim


def _write_model(tmp_path, model_id: str, input_id: str, output_id: str):
    path = tmp_path / f"{model_id}.json"
    path.write_text(
        json.dumps(
            {
                "model_id": model_id,
                "version": "1",
                "calibration_status": "expert_prior_unvalidated",
                "nodes": [
                    {"id": input_id, "type": "prior", "prior": 0.2},
                    {
                        "id": output_id,
                        "type": "noisy_or",
                        "parents": [input_id],
                        "weights": {input_id: 0.8},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _assessment(claim_id: str, support: float) -> ClaimAssessment:
    return ClaimAssessment(
        claim_id=claim_id,
        opinion=ClaimOpinion(claim_id, support=support, uncertainty=1.0 - support),
        support_index=support,
    )


def test_registry_selects_all_matching_models_without_case_priority(tmp_path):
    _write_model(tmp_path, "property_taking", "taking_action", "taking_supported")
    _write_model(tmp_path, "conduct_result", "conduct", "causation")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "1",
                "models": [
                    {
                        "model_id": "property_taking",
                        "path": "property_taking.json",
                        "domains": ["property_rights"],
                        "trigger_predicates": ["taking_property"],
                        "input_map": {"taking_property": "taking_action"},
                        "derived_nodes": ["taking_supported"],
                        "priority": 0,
                    },
                    {
                        "model_id": "conduct_result",
                        "path": "conduct_result.json",
                        "domains": ["personal_rights"],
                        "trigger_predicates": ["violence"],
                        "input_map": {"violence": "conduct"},
                        "derived_nodes": ["causation"],
                        "priority": 0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    claims = [
        EvidenceClaim("C-TAKE", "甲", "taking_property"),
        EvidenceClaim("C-VIOLENCE", "甲", "violence"),
    ]

    selected = BayesianModelRegistry(registry_path).select(
        ["property_rights"], claims
    )

    assert [item.model_id for item in selected] == [
        "property_taking",
        "conduct_result",
    ]
    assert {item.priority for item in selected} == {0}


def test_tool_runs_multiple_models_and_returns_audit_trace(tmp_path):
    _write_model(tmp_path, "property_taking", "taking_action", "taking_supported")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "1",
                "models": [
                    {
                        "model_id": "property_taking",
                        "path": "property_taking.json",
                        "domains": ["property_rights"],
                        "trigger_predicates": ["taking_property"],
                        "input_map": {"taking_property": "taking_action"},
                        "derived_nodes": ["taking_supported"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    claim = EvidenceClaim("C-TAKE", "甲", "taking_property")

    result = BayesianEvidenceTool(BayesianModelRegistry(registry_path)).evaluate(
        ["property_rights"], [claim], [_assessment(claim.claim_id, 0.8)]
    )

    assert result.selected_model_ids == ["property_taking"]
    run = result.runs[0]
    assert run.model_id == "property_taking"
    assert run.version == "1"
    assert run.calibration_status == "expert_prior_unvalidated"
    assert len(run.parameter_hash) == 64
    assert run.input_claim_ids == ["C-TAKE"]
    assert run.derived_values["taking_supported"] > 0.2


def test_tool_returns_empty_result_when_no_model_matches(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"version": "1", "models": []}), encoding="utf-8"
    )

    result = BayesianEvidenceTool(BayesianModelRegistry(registry_path)).evaluate(
        ["unknown"], [], []
    )

    assert result.selected_model_ids == []
    assert result.runs == []


def test_registry_rejects_priority_and_missing_models(tmp_path):
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "1",
                "models": [
                    {
                        "model_id": "special_case",
                        "path": "missing.json",
                        "domains": [],
                        "trigger_predicates": ["violence"],
                        "input_map": {"violence": "conduct"},
                        "derived_nodes": ["causation"],
                        "priority": 10,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelValidationError, match="equal priority"):
        BayesianModelRegistry(registry_path)

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    data["models"][0]["priority"] = 0
    registry_path.write_text(json.dumps(data), encoding="utf-8")
    registry = BayesianModelRegistry(registry_path)

    with pytest.raises(ModelValidationError, match="model file does not exist"):
        BayesianEvidenceTool(registry).evaluate(
            [], [EvidenceClaim("C", "甲", "violence")], [_assessment("C", 0.7)]
        )
