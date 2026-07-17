"""Replay categorized synthetic cases through the real workflow."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from case_agent_demo.evidence_intake import _extract_docx_text
from case_agent_demo.models import Material, MaterialType, WorkflowResult
from case_agent_demo.workflow import CaseWorkflow


def discover_cases(root: str | Path) -> list[Path]:
    return sorted(path.parent for path in Path(root).rglob("case.json"))


def load_case(case_dir: str | Path) -> tuple[dict[str, Any], list[Material]]:
    case_path = Path(case_dir)
    config = json.loads((case_path / "case.json").read_text(encoding="utf-8"))
    materials = []
    for item in config["materials"]:
        source_path = case_path / str(item["path"])
        content = (
            _extract_docx_text(source_path)
            if source_path.suffix.casefold() == ".docx"
            else source_path.read_text(encoding="utf-8")
        )
        materials.append(
            Material(
                material_id=str(item["material_id"]),
                material_type=MaterialType(str(item["material_type"])),
                content=content,
                source_path=str(source_path.resolve()),
            )
        )
    return config, materials


def replay_case(case_dir: str | Path, workflow: CaseWorkflow | None = None) -> WorkflowResult:
    config, materials = load_case(case_dir)
    runner = workflow or CaseWorkflow.demo()
    return runner.run(
        materials,
        confirmed_case_type=str(config.get("case_type", "")),
        authority_verifications=config.get("authority_verifications"),
    )


def validate_replay(config: dict[str, Any], result: WorkflowResult) -> list[str]:
    expected = config.get("expected", {})
    selected_models = set((result.bayesian_result or {}).get("selected_model_ids", []))
    citations = {(item.law_name, item.article) for item in result.legal_matches}
    articles = {article for _, article in citations}
    errors: list[str] = []

    missing_models = set(expected.get("bayesian_models", [])) - selected_models
    if missing_models:
        errors.append(f"missing Bayesian models: {sorted(missing_models)}")
    missing_articles = set(expected.get("must_include_articles", [])) - articles
    if missing_articles:
        errors.append(f"missing legal articles: {sorted(missing_articles)}")
    forbidden_articles = set(expected.get("must_exclude_articles", [])) & articles
    if forbidden_articles:
        errors.append(f"unexpected legal articles: {sorted(forbidden_articles)}")
    runs = (result.bayesian_result or {}).get("runs", [])
    expected_run_count = expected.get("bayesian_run_count")
    if expected_run_count is not None and len(runs) != int(expected_run_count):
        errors.append(f"expected {expected_run_count} Bayesian run(s), got {len(runs)}")
    for node_id, minimum in expected.get("derived_min", {}).items():
        values = [
            float(run.get("derived_values", {}).get(node_id))
            for run in runs
            if node_id in run.get("derived_values", {})
        ]
        if not values or max(values) < float(minimum):
            errors.append(f"derived node {node_id} did not reach {minimum}")

    primary = expected.get("primary_claim")
    if isinstance(primary, dict):
        candidates = [
            claim
            for claim in result.case_graph.claims
            if claim.subject == primary.get("subject")
            and claim.behavior_type == primary.get("predicate")
            and (claim.target_person or claim.object) == primary.get("target", "")
        ]
        if len(candidates) != 1:
            errors.append(f"expected one primary claim, got {len(candidates)}")
        else:
            claim = candidates[0]
            source_count = len(set(claim.supporting_node_ids))
            if source_count < int(primary.get("min_sources", 1)):
                errors.append(f"primary claim has only {source_count} supporting source(s)")
            assessment = next(
                (item for item in result.claim_assessments if item.claim_id == claim.claim_id),
                None,
            )
            if assessment is None or assessment.status != primary.get("status"):
                actual = assessment.status if assessment is not None else "missing"
                errors.append(f"primary claim status is {actual}, expected {primary.get('status')}")
    return errors


def replay_summary(case_dir: Path, result: WorkflowResult, errors: list[str]) -> dict[str, Any]:
    return {
        "case": case_dir.name,
        "claims": [
            {
                "claim_id": claim.claim_id,
                "subject": claim.subject,
                "predicate": claim.behavior_type,
                "target": claim.target_person or claim.object,
                "supporting_nodes": claim.supporting_node_ids,
            }
            for claim in result.case_graph.claims
        ],
        "assessments": [asdict(item) for item in result.claim_assessments],
        "bayesian_models": (result.bayesian_result or {}).get("selected_model_ids", []),
        "legal_matches": [
            {"law": item.law_name, "article": item.article} for item in result.legal_matches
        ],
        "validation_errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay synthetic multi-case evidence fixtures")
    parser.add_argument("--root", default="测试用例")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    workflow = CaseWorkflow.demo()
    summaries = []
    for case_dir in discover_cases(args.root):
        config, _ = load_case(case_dir)
        result = replay_case(case_dir, workflow)
        errors = validate_replay(config, result)
        summaries.append(replay_summary(case_dir, result, errors))

    payload = json.dumps(summaries, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 1 if any(item["validation_errors"] for item in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
