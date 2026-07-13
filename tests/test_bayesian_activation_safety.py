import json

from case_agent_demo.bayesian_tool import BayesianEvidenceTool, BayesianModelRegistry
from case_agent_demo.models import ClaimAssessment, ClaimOpinion, EvidenceClaim


def _registry(tmp_path):
    (tmp_path / "relation.json").write_text(
        json.dumps(
            {
                "model_id": "generic_relation",
                "version": "1",
                "calibration_status": "expert_prior_unvalidated",
                "nodes": [
                    {"id": "conduct", "type": "prior", "prior": 0.2},
                    {"id": "result", "type": "prior", "prior": 0.2},
                    {
                        "id": "relation",
                        "type": "logistic",
                        "parents": ["conduct", "result"],
                        "intercept": -2.0,
                        "weights": {"conduct": 1.5, "result": 1.0},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "registry.json").write_text(
        json.dumps(
            {
                "version": "1",
                "models": [
                    {
                        "model_id": "generic_relation",
                        "path": "relation.json",
                        "domains": ["example_domain"],
                        "trigger_predicates": ["alleged_conduct", "observed_result"],
                        "input_map": {
                            "alleged_conduct": "conduct",
                            "observed_result": "result",
                        },
                        "derived_nodes": ["relation"],
                        "anchor_inputs": ["conduct"],
                        "required_inputs": ["conduct", "result"],
                        "priority": 0,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return BayesianModelRegistry(tmp_path / "registry.json")


def _assessment(claim_id: str, support: float, opposition: float, uncertainty: float):
    return ClaimAssessment(
        claim_id=claim_id,
        opinion=ClaimOpinion(claim_id, support, opposition, uncertainty),
        support_index=support + 0.5 * uncertainty,
    )


def test_domain_label_alone_cannot_select_or_run_a_model(tmp_path):
    result = BayesianEvidenceTool(_registry(tmp_path)).evaluate(
        ["example_domain"],
        [EvidenceClaim("C-X", "甲", "unrelated")],
        [_assessment("C-X", 0.6, 0.0, 0.4)],
    )

    assert result.selected_model_ids == []
    assert result.runs == []
    assert [item.reason for item in result.abstentions] == [
        "no_matching_relation_component"
    ]


def test_ambiguous_or_denial_only_claim_does_not_activate_positive_inference(tmp_path):
    claim = EvidenceClaim(
        "C-CONDUCT",
        "甲",
        "alleged_conduct",
        metadata={"assertion_roles": ["defense_response"]},
    )
    result = BayesianEvidenceTool(_registry(tmp_path)).evaluate(
        [],
        [claim],
        [_assessment(claim.claim_id, 0.0, 0.4, 0.6)],
    )

    assert result.runs == []
    assert result.abstentions
    assert result.abstentions[0].reason == "missing_allegation_anchor"


def test_missing_required_input_abstains_instead_of_filling_model_prior(tmp_path):
    claim = EvidenceClaim(
        "C-CONDUCT",
        "甲",
        "alleged_conduct",
        metadata={"assertion_roles": ["allegation"]},
    )
    result = BayesianEvidenceTool(_registry(tmp_path)).evaluate(
        [],
        [claim],
        [_assessment(claim.claim_id, 0.5, 0.0, 0.5)],
    )

    assert result.runs == []
    assert result.abstentions[0].reason == "missing_required_inputs"
    assert result.abstentions[0].missing_inputs == ["result"]
