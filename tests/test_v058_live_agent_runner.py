from __future__ import annotations

import json
from collections import defaultdict

from scripts.run_v058_live_agent_acceptance import run_live_acceptance
from tests.semantic_runtime import SemanticFixtureRuntime
from tests.v058_case_helpers import CORPUS_ROOT, discover_v058_cases, load_json


class UnavailableRuntime:
    available = False


def test_live_runner_reports_model_unavailable_without_fallback(tmp_path):
    report = run_live_acceptance(
        corpus_root=CORPUS_ROOT,
        output_root=tmp_path,
        runtime=UnavailableRuntime(),
    )

    assert report["status"] == "model_unavailable"
    assert report["fallback_used"] is False
    assert report["keyword_fallback_used"] is False
    assert (tmp_path / report["run_id"] / "summary.json").is_file()


def test_live_runner_compares_agent_output_with_golden_assertions(tmp_path):
    case_dir = discover_v058_cases()[0]
    semantic = load_json(case_dir / "expected" / "semantic_assertions.json")
    facts_by_material = defaultdict(list)
    for item in semantic["assertions"]:
        facts_by_material[item["source_material_id"]].append(item["agent_fact"])

    report = run_live_acceptance(
        corpus_root=case_dir,
        output_root=tmp_path,
        runtime=SemanticFixtureRuntime(dict(facts_by_material)),
    )

    assert report["status"] == "completed"
    assert report["case_count"] == 1
    assert report["material_count"] > 0
    assert report["missing_expected_count"] == 0
    assert report["keyword_fallback_used"] is False
    persisted = json.loads(
        (tmp_path / report["run_id"] / "summary.json").read_text(encoding="utf-8")
    )
    assert persisted["run_id"] == report["run_id"]
