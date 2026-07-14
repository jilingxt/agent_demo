from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.v058_case_helpers import (
    CORPUS_ROOT,
    assert_expected_outcome,
    discover_v058_cases,
    load_json,
    replay_v058_case,
)


ROOT = Path(__file__).resolve().parents[1]


def build_report(
    corpus_root: Path = CORPUS_ROOT,
    live_summary_path: Path | None = None,
) -> dict[str, Any]:
    live_cases = _load_live_cases(live_summary_path)
    cases = []
    for case_dir in discover_v058_cases(corpus_root):
        config = load_json(case_dir / "case.json")
        expected = load_json(case_dir / "expected" / "expected_outcome.json")
        result = replay_v058_case(case_dir)
        deterministic_status = "passed"
        deterministic_error = ""
        try:
            assert_expected_outcome(case_dir, result)
        except AssertionError as exc:
            deterministic_status = "failed"
            deterministic_error = str(exc)

        bayesian = result.bayesian_result or {}
        cases.append(
            {
                "case_id": config["case_id"],
                "directory": case_dir.name,
                "law": config["law_title"],
                "article": config["article"],
                "complexity_type": config["complexity_type"],
                "material_hashes": _material_hashes(case_dir, config["materials"]),
                "claim_assessments": [
                    {
                        "claim_id": item.claim_id,
                        "status": item.status,
                        "support_index": item.support_index,
                        "uncertainty": item.opinion.uncertainty if item.opinion else 1.0,
                        "conflict_index": item.opinion.conflict if item.opinion else 0.0,
                    }
                    for item in result.claim_assessments
                ],
                "bayesian_models": list(bayesian.get("selected_model_ids", [])),
                "bayesian_abstentions": list(bayesian.get("abstentions", [])),
                "legal_articles": sorted({item.article for item in result.legal_matches}),
                "validation_issue_types": sorted(
                    {item.issue_type for item in result.validation_issues}
                ),
                "model_versions": result.model_versions,
                "parameter_hashes": dict(bayesian.get("parameter_hashes", {})),
                "expected_contract": {
                    "claims": expected["required_claims"],
                    "bayesian_models": expected["expected_bayesian_models"],
                    "legal_articles": expected["required_legal_articles"],
                    "validation_issue_types": expected["required_issue_types"],
                },
                "deterministic_status": deterministic_status,
                "deterministic_error": deterministic_error,
                "live_status": live_cases.get(config["case_id"], {"status": "not_run"}),
            }
        )

    sampling = load_json(corpus_root / "sampling_manifest.json")
    return {
        "schema_version": "1.0",
        "version": "0.58.0",
        "git_revision": _git_revision(),
        "sampling": {
            "seed": sampling["seed"],
            "accepted": sampling["accepted"],
            "rejected": sampling["rejected"],
        },
        "summary": {
            "case_count": len(cases),
            "passed_count": sum(item["deterministic_status"] == "passed" for item in cases),
            "failed_count": sum(item["deterministic_status"] == "failed" for item in cases),
        },
        "cases": cases,
    }


def write_report(report: dict[str, Any], output_root: Path) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "summary.json"
    markdown_path = output_root / "summary.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [
        "# v0.58 十案验收摘要",
        "",
        f"- 随机种子：`{report['sampling']['seed']}`",
        f"- 案例总数：`{report['summary']['case_count']}`",
        f"- 确定性通过：`{report['summary']['passed_count']}`",
        f"- 确定性失败：`{report['summary']['failed_count']}`",
        f"- Git 修订：`{report['git_revision']}`",
        "",
        "| 案例 | 法律条文 | 复杂情形 | 结果 | 贝叶斯组件/弃权 |",
        "|---|---|---|---|---|",
    ]
    for item in report["cases"]:
        bayesian = ", ".join(item["bayesian_models"]) or "安全弃权"
        rows.append(
            f"| {item['case_id']} | {item['law']}{item['article']} | "
            f"{item['complexity_type']} | {item['deterministic_status']} | {bayesian} |"
        )
    rows.extend(
        [
            "",
            "> 贝叶斯派生值是版本化专家参数下的证据关系支持值，不是事实概率、有罪概率或处罚概率。",
        ]
    )
    markdown_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _material_hashes(case_dir: Path, materials: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item["path"]).replace("\\", "/"): hashlib.sha256(
            (case_dir / item["path"]).read_bytes()
        ).hexdigest()
        for item in materials
    }


def _load_live_cases(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        candidates = sorted((ROOT / "artifacts" / "v058-live-agent").glob("*/summary.json"))
        path = candidates[-1] if candidates else None
    if path is None or not path.is_file():
        return {}
    data = load_json(path)
    return {
        str(item["case_id"]): {
            "status": data.get("status", "unknown"),
            "missing_expected_count": sum(
                len(material.get("missing_expected", [])) for material in item.get("materials", [])
            ),
            "unexpected_actual_count": sum(
                len(material.get("unexpected_actual", [])) for material in item.get("materials", [])
            ),
            "unresolved_count": sum(
                int(material.get("unresolved_count", 0)) for material in item.get("materials", [])
            ),
            "fallback_used": bool(data.get("fallback_used", False)),
            "keyword_fallback_used": bool(data.get("keyword_fallback_used", False)),
        }
        for item in data.get("cases", [])
    }


def _git_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the v0.58 ten-case acceptance report.")
    parser.add_argument("--corpus", type=Path, default=CORPUS_ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "v058-acceptance")
    parser.add_argument("--live-summary", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    report = build_report(args.corpus, args.live_summary)
    paths = write_report(report, args.output)
    if args.verify and report["summary"]["failed_count"]:
        return 1
    print("\n".join(str(path.resolve()) for path in paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
