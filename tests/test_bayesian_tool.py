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


def _conduct_registry(tmp_path):
    path = tmp_path / "conduct.json"
    path.write_text(
        json.dumps({
            "model_id": "conduct_result",
            "version": "1",
            "calibration_status": "expert_prior_unvalidated",
            "nodes": [
                {"id": "conduct", "type": "prior", "prior": 0.2},
                {"id": "result_exists", "type": "prior", "prior": 0.2},
                {"id": "causation", "type": "logistic", "parents": ["conduct", "result_exists"], "intercept": -2, "weights": {"conduct": 2, "result_exists": 1}},
            ],
        }),
        encoding="utf-8",
    )
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"version": "1", "models": [{
            "model_id": "conduct_result",
            "path": path.name,
            "domains": [],
            "trigger_predicates": ["violence", "injury_exists"],
            "input_map": {"violence": "conduct", "injury_exists": "result_exists"},
            "derived_nodes": ["causation"],
            "anchor_inputs": ["conduct"],
            "priority": 0,
        }]}),
        encoding="utf-8",
    )
    return BayesianModelRegistry(registry_path)


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
    assert run.soft_evidence_sources == {"taking_action": ["C-TAKE"]}
    assert run.derived_values["taking_supported"] > 0.2


def test_tool_lineage_only_keeps_claims_that_contribute_the_selected_maximum(tmp_path):
    _write_model(tmp_path, "property_taking", "taking_action", "taking_supported")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "1",
                "models": [{
                    "model_id": "property_taking",
                    "path": "property_taking.json",
                    "domains": [],
                    "trigger_predicates": ["taking_property"],
                    "input_map": {"taking_property": "taking_action"},
                    "derived_nodes": ["taking_supported"],
                    "priority": 0,
                }],
            }
        ),
        encoding="utf-8",
    )
    claims = [
        EvidenceClaim("C-WEAK", "甲", "taking_property", target_person="手机", event_id="E1"),
        EvidenceClaim("C-STRONG", "甲", "taking_property", target_person="手机", event_id="E1"),
    ]

    result = BayesianEvidenceTool(BayesianModelRegistry(registry_path)).evaluate(
        [], claims, [_assessment("C-WEAK", 0.3), _assessment("C-STRONG", 0.8)]
    )

    assert result.runs[0].input_claim_ids == ["C-STRONG"]
    assert result.runs[0].soft_evidence_sources == {"taking_action": ["C-STRONG"]}


def test_registry_rejects_model_id_and_node_mapping_mismatches(tmp_path):
    model_path = _write_model(tmp_path, "actual", "input", "output")
    base_entry = {
        "model_id": "declared",
        "path": model_path.name,
        "domains": [],
        "trigger_predicates": ["predicate"],
        "input_map": {"predicate": "input"},
        "derived_nodes": ["output"],
        "priority": 0,
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps({"version": "1", "models": [base_entry]}), encoding="utf-8"
    )
    with pytest.raises(ModelValidationError, match="does not match"):
        BayesianModelRegistry(registry_path)

    base_entry["model_id"] = "actual"
    base_entry["input_map"] = {"predicate": "missing"}
    registry_path.write_text(
        json.dumps({"version": "1", "models": [base_entry]}), encoding="utf-8"
    )
    with pytest.raises(ModelValidationError, match="unknown nodes"):
        BayesianModelRegistry(registry_path)


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
    data["models"][0]["priority"] = 0.5
    registry_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ModelValidationError, match="integer 0"):
        BayesianModelRegistry(registry_path)

    data["models"][0]["priority"] = 0
    registry_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ModelValidationError, match="model file does not exist"):
        BayesianModelRegistry(registry_path)


def test_unknown_assessment_is_omitted_instead_of_becoming_false(tmp_path):
    claim = EvidenceClaim("C-UNKNOWN", "甲", "violence", event_id="E1")

    result = BayesianEvidenceTool(_conduct_registry(tmp_path)).evaluate(
        [], [claim], [ClaimAssessment(claim_id=claim.claim_id, status="unassessed")]
    )

    assert result.runs == []


def test_model_runs_are_separated_by_event_and_anchor_actor(tmp_path):
    claims = [
        EvidenceClaim("C-A", "甲", "violence", target_person="乙", event_id="E1"),
        EvidenceClaim("C-C", "丙", "violence", target_person="丁", event_id="E2"),
        EvidenceClaim("C-D", "丁", "injury_exists", target_person="丁", event_id="E2"),
    ]
    assessments = [_assessment(claim.claim_id, 0.8) for claim in claims]

    result = BayesianEvidenceTool(_conduct_registry(tmp_path)).evaluate([], claims, assessments)

    assert len(result.runs) == 2
    runs = {run.group_key: run for run in result.runs}
    assert runs["E1|甲|乙"].soft_evidence == {"conduct": 0.8}
    assert runs["E2|丙|丁"].soft_evidence == {"conduct": 0.8, "result_exists": 0.8}


def test_same_event_multiple_actors_get_separate_runs_with_shared_result(tmp_path):
    claims = [
        EvidenceClaim("C-A", "甲", "violence", target_person="乙", event_id="E1"),
        EvidenceClaim("C-C", "丙", "violence", target_person="乙", event_id="E1"),
        EvidenceClaim("C-B", "乙", "injury_exists", target_person="乙", event_id="E1"),
    ]

    result = BayesianEvidenceTool(_conduct_registry(tmp_path)).evaluate(
        [], claims, [_assessment(claim.claim_id, 0.8) for claim in claims]
    )

    assert {run.group_key for run in result.runs} == {"E1|甲|乙", "E1|丙|乙"}
    assert all("result_exists" in run.soft_evidence for run in result.runs)


def test_missing_event_id_does_not_join_separate_claims(tmp_path):
    claims = [
        EvidenceClaim("C-A", "甲", "violence", target_person="乙"),
        EvidenceClaim("C-B", "乙", "injury_exists", target_person="乙"),
    ]

    result = BayesianEvidenceTool(_conduct_registry(tmp_path)).evaluate(
        [], claims, [_assessment(claim.claim_id, 0.8) for claim in claims]
    )

    assert len(result.runs) == 1
    assert result.runs[0].soft_evidence == {"conduct": 0.8}


def test_same_event_different_targets_are_not_joined(tmp_path):
    claims = [
        EvidenceClaim("C-A", "甲", "violence", target_person="乙", event_id="E1"),
        EvidenceClaim("C-WRONG", "甲", "injury_exists", target_person="丙", event_id="E1"),
        EvidenceClaim("C-RIGHT", "乙", "injury_exists", target_person="乙", event_id="E1"),
    ]

    result = BayesianEvidenceTool(_conduct_registry(tmp_path)).evaluate(
        [], claims, [_assessment(claim.claim_id, 0.8) for claim in claims]
    )

    assert len(result.runs) == 1
    assert result.runs[0].input_claim_ids == ["C-A", "C-RIGHT"]
    assert "C-WRONG" not in result.runs[0].input_claim_ids
