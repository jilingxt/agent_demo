from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from case_agent_demo.agent_runtime import (
    _extract_message_content,
    _strip_json_fence,
)
from case_agent_demo.agents import PicAgent, ReportImageAgent, TextAgent
from case_agent_demo.config import ModelProfiles
from case_agent_demo.evidence_intake import _extract_docx_text
from case_agent_demo.llm_clients import Dsv4Client
from case_agent_demo.models import Fact, Material, MaterialType
from case_agent_demo.prompt_config import PromptLoader


@dataclass
class RecordingAgentRuntime:
    client: Any
    prompt_loader: PromptLoader = field(default_factory=PromptLoader)
    records: list[dict[str, Any]] = field(default_factory=list)
    available: bool = True

    def run_json(
        self,
        prompt_name: str,
        profile: Any,
        user_input: str,
        fallback: Callable[[], Any],
        parser: Callable[[dict[str, Any]], Any],
    ) -> Any:
        material_id = _material_id_from_input(user_input)
        record: dict[str, Any] = {
            "material_id": material_id,
            "prompt_name": prompt_name,
            "model": profile.model_name,
            "raw_content": "",
            "error": "",
            "fallback_used": False,
        }
        try:
            system_prompt = self.prompt_loader.load(prompt_name)
            payload = self.client.build_chat_payload(profile, system_prompt, user_input)
            response = self.client.chat_completions(payload)
            content = _extract_message_content(response)
            record["raw_content"] = content
            parsed = json.loads(_strip_json_fence(content))
            result = parser(parsed)
        except Exception as exc:  # The report must survive provider and parse failures.
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["fallback_used"] = True
            result = fallback()
        self.records.append(record)
        return result


def run_live_acceptance(
    corpus_root: str | Path,
    output_root: str | Path,
    runtime: Any | None = None,
) -> dict[str, Any]:
    corpus_root = Path(corpus_root)
    output_root = Path(output_root)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    if runtime is None:
        runtime = _configured_runtime()
    if not _runtime_available(runtime):
        summary = _base_summary(run_id, "model_unavailable")
        _write_json(run_dir / "summary.json", summary)
        return summary

    profiles = ModelProfiles.from_runtime_config()
    agents = {
        MaterialType.STATEMENT: TextAgent(runtime=runtime, profile=profiles.text),
        MaterialType.EVIDENCE_IMAGE: PicAgent(runtime=runtime, profile=profiles.text),
        MaterialType.REPORT_IMAGE: ReportImageAgent(
            runtime=runtime,
            profile=profiles.reasoning,
        ),
    }
    case_dirs = _discover_cases(corpus_root)
    total_materials = 0
    missing_count = 0
    unexpected_count = 0
    unresolved_count = 0
    case_reports: list[dict[str, Any]] = []

    for case_dir in case_dirs:
        config = _load_json(case_dir / "case.json")
        golden = _load_json(case_dir / "expected" / "semantic_assertions.json")
        expected_by_material: dict[str, list[dict[str, Any]]] = {}
        for item in golden.get("assertions", []):
            expected_by_material.setdefault(str(item["source_material_id"]), []).append(
                dict(item["agent_fact"])
            )

        material_reports: list[dict[str, Any]] = []
        for item in config.get("materials", []):
            material_id = str(item["material_id"])
            material_type = MaterialType(str(item["material_type"]))
            source_path = case_dir / str(item["path"])
            material = Material(
                material_id=material_id,
                material_type=material_type,
                content=_load_material_content(source_path),
                source_path=str(source_path.resolve()),
                metadata={"title": item.get("title", ""), "role": item.get("role", "")},
            )
            facts = agents[material_type].runnable.invoke(material)
            expected = [_expected_projection(value, material_id) for value in expected_by_material.get(material_id, [])]
            actual = [_fact_projection(value) for value in facts]
            missing, unexpected = _semantic_diff(expected, actual)
            unresolved = sum(
                1 for fact in facts if fact.metadata.get("semantic_status") == "unresolved"
            )
            total_materials += 1
            missing_count += len(missing)
            unexpected_count += len(unexpected)
            unresolved_count += unresolved
            material_report = {
                "material_id": material_id,
                "material_type": material_type.value,
                "source_path": str(source_path),
                "expected": expected,
                "actual": actual,
                "missing_expected": missing,
                "unexpected_actual": unexpected,
                "unresolved_count": unresolved,
                "runtime_records": _records_for_material(runtime, material_id),
            }
            material_reports.append(material_report)
            _write_json(run_dir / "materials" / f"{material_id}.json", material_report)
        case_reports.append(
            {
                "case_id": config.get("case_id", case_dir.name),
                "case_dir": str(case_dir),
                "materials": material_reports,
            }
        )

    fallback_used = any(
        bool(record.get("fallback_used"))
        for record in getattr(runtime, "records", [])
        if isinstance(record, dict)
    )
    status = "completed_with_errors" if fallback_used or unresolved_count else "completed"
    summary = {
        **_base_summary(run_id, status),
        "case_count": len(case_dirs),
        "material_count": total_materials,
        "missing_expected_count": missing_count,
        "unexpected_actual_count": unexpected_count,
        "unresolved_count": unresolved_count,
        "fallback_used": fallback_used,
        "cases": case_reports,
    }
    _write_json(run_dir / "summary.json", summary)
    return summary


def _configured_runtime() -> RecordingAgentRuntime | None:
    try:
        return RecordingAgentRuntime(Dsv4Client.from_config_file())
    except (FileNotFoundError, RuntimeError):
        return None


def _runtime_available(runtime: Any | None) -> bool:
    if runtime is None:
        return False
    if hasattr(runtime, "available"):
        return bool(runtime.available)
    if hasattr(runtime, "client"):
        return runtime.client is not None
    return callable(getattr(runtime, "run_json", None))


def _discover_cases(root: Path) -> list[Path]:
    if (root / "case.json").is_file():
        return [root]
    return sorted(path.parent for path in root.glob("*/case.json"))


def _load_material_content(path: Path) -> str:
    if path.suffix.casefold() == ".docx":
        return _extract_docx_text(path)
    if path.suffix.casefold() in {".txt", ".md", ".json"}:
        return path.read_text(encoding="utf-8")
    return ""


def _expected_projection(value: dict[str, Any], material_id: str) -> dict[str, str]:
    return {
        "source_material_id": material_id,
        "actor": str(value.get("actor", "")),
        "target_person": str(value.get("target_person", "")),
        "object": str(value.get("object", "")),
        "predicate": str(value.get("predicate", "")),
        "stance": str(value.get("stance", "")),
        "event_id": str(value.get("event_id", "")),
        "source_group": str(value.get("source_group", "")),
        "origin_evidence": str(value.get("origin_evidence", "")),
    }


def _fact_projection(fact: Fact) -> dict[str, str]:
    metadata = fact.metadata
    return {
        "source_material_id": fact.source_material_id,
        "actor": str(metadata.get("actor", fact.person)),
        "target_person": str(metadata.get("target_person", "")),
        "object": str(metadata.get("object", fact.object)),
        "predicate": str(metadata.get("predicate", "")),
        "stance": str(metadata.get("stance", "")),
        "event_id": str(metadata.get("event_id", "")),
        "source_group": str(metadata.get("source_group", "")),
        "origin_evidence": str(metadata.get("origin_evidence", "")),
    }


def _semantic_diff(
    expected: list[dict[str, str]],
    actual: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    expected_counter = Counter(_projection_key(item) for item in expected)
    actual_counter = Counter(_projection_key(item) for item in actual)
    missing = [dict(zip(_PROJECTION_FIELDS, key)) for key in (expected_counter - actual_counter).elements()]
    unexpected = [dict(zip(_PROJECTION_FIELDS, key)) for key in (actual_counter - expected_counter).elements()]
    return missing, unexpected


_PROJECTION_FIELDS = (
    "source_material_id",
    "actor",
    "target_person",
    "object",
    "predicate",
    "stance",
    "event_id",
    "source_group",
    "origin_evidence",
)


def _projection_key(item: dict[str, str]) -> tuple[str, ...]:
    return tuple(item.get(field, "") for field in _PROJECTION_FIELDS)


def _records_for_material(runtime: Any, material_id: str) -> list[dict[str, Any]]:
    return [
        dict(record)
        for record in getattr(runtime, "records", [])
        if isinstance(record, dict) and record.get("material_id") == material_id
    ]


def _material_id_from_input(user_input: str) -> str:
    match = re.search(r"material_id:\s*([^\r\n]+)", user_input)
    return match.group(1).strip() if match else ""


def _base_summary(run_id: str, status: str) -> dict[str, Any]:
    return {
        "schema_version": "0.58",
        "run_id": run_id,
        "status": status,
        "case_count": 0,
        "material_count": 0,
        "missing_expected_count": 0,
        "unexpected_actual_count": 0,
        "unresolved_count": 0,
        "fallback_used": False,
        "keyword_fallback_used": False,
        "cases": [],
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run v0.58 live semantic Agent acceptance.")
    parser.add_argument("--corpus", type=Path, default=Path("测试用例") / "v058随机条文")
    parser.add_argument("--output", type=Path, default=Path("artifacts") / "v058-live-agent")
    args = parser.parse_args()
    report = run_live_acceptance(args.corpus, args.output)
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
