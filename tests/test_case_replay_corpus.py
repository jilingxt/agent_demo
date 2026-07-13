from __future__ import annotations

from pathlib import Path

import pytest

from case_agent_demo.case_replay import discover_cases, load_case, replay_case, validate_replay
from case_agent_demo.workflow import CaseWorkflow


ROOT = Path(__file__).resolve().parents[1] / "测试用例"
CASES = discover_cases(ROOT)


@pytest.mark.parametrize("case_dir", CASES, ids=lambda path: path.name)
def test_categorized_case_replay_matches_expected_models_and_laws(case_dir):
    config, _ = load_case(case_dir)
    result = replay_case(case_dir, CaseWorkflow.demo())
    assert validate_replay(config, result) == []


def test_injury_case_uses_one_multi_source_conduct_claim_and_one_bayesian_run():
    case_dir = ROOT / "故意伤害_多源印证"
    result = replay_case(case_dir, CaseWorkflow.demo())
    claims = [
        claim
        for claim in result.case_graph.claims
        if claim.subject == "李文杰"
        and claim.behavior_type == "violence"
        and claim.target_person == "贺显作"
    ]
    assert len(claims) == 1
    assert len(set(claims[0].supporting_node_ids)) >= 4
    assessment = next(
        item for item in result.claim_assessments if item.claim_id == claims[0].claim_id
    )
    assert assessment.status == "supported"

    runs = [
        run
        for run in result.bayesian_result["runs"]
        if run["model_id"] == "conduct_result"
    ]
    assert len(runs) == 1
    assert runs[0]["derived_values"]["causation"] >= 0.5
