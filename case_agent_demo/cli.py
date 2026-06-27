from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from case_agent_demo.evidence_intake import EvidenceIntake, ensure_evidence_vault
from case_agent_demo.models import Material, MaterialType
from case_agent_demo.vision_tools import QwenImageEvidenceTool
from case_agent_demo.workflow import CaseWorkflow


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def sample_materials() -> list[Material]:
    return [
        Material("S1", MaterialType.STATEMENT, "张三称20时在家，李四称20时看见张三在现场。"),
        Material("P1", MaterialType.EVIDENCE_IMAGE, "现场照片显示一名男子和被损坏门锁。"),
        Material("R1", MaterialType.REPORT_IMAGE, "监控研判报告：20时05分张三出现在现场附近。签章清晰。"),
    ]


def _load_materials(args: argparse.Namespace) -> list[Material]:
    if args.evidence_dir:
        return EvidenceIntake(args.evidence_dir).load_materials()
    if args.sample:
        return sample_materials()
    return []


def attach_qwen_vision_tool(workflow: CaseWorkflow) -> None:
    vision_tool = QwenImageEvidenceTool.from_config_file(workflow.model_profiles.vision)
    workflow.pic_agent.vision_tool = vision_tool
    workflow.report_image_agent.vision_tool = vision_tool


def should_enable_qwen_vision(args: argparse.Namespace) -> bool:
    return bool(args.evidence_dir and not args.disable_qwen_vision)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the case evidence multi-agent demo.")
    parser.add_argument("--sample", action="store_true", help="Run with built-in sample materials.")
    parser.add_argument(
        "--case-type",
        default="盗窃类案件",
        help="Human-confirmed case type for demo execution.",
    )
    parser.add_argument(
        "--evidence-dir",
        help="Load materials from an evidence_vault directory.",
    )
    parser.add_argument(
        "--init-evidence-vault",
        nargs="?",
        const="evidence_vault",
        help="Create evidence vault folders, defaulting to ./evidence_vault.",
    )
    parser.add_argument(
        "--disable-qwen-vision",
        action="store_true",
        help="Do not call Qwen vision API for image materials; use extracted text or placeholders instead.",
    )
    args = parser.parse_args()

    if args.init_evidence_vault:
        root = ensure_evidence_vault(Path(args.init_evidence_vault))
        print(f"Evidence vault initialized: {root}")
        return

    workflow = CaseWorkflow.demo()
    if should_enable_qwen_vision(args):
        attach_qwen_vision_tool(workflow)
    materials = _load_materials(args)
    suggestion = workflow.suggest_case_type(materials)
    result = workflow.run(materials, confirmed_case_type=args.case_type)

    print("=== Case Type Suggestion ===")
    print(json.dumps(suggestion, ensure_ascii=False, indent=2, default=_json_default))
    print("\n=== Evidence Materials ===")
    print(json.dumps(materials, ensure_ascii=False, indent=2, default=_json_default))
    print("\n=== Open Source Stack ===")
    print(json.dumps(workflow.open_source_stack, ensure_ascii=False, indent=2, default=_json_default))
    print("\n=== Model Profiles ===")
    print(json.dumps(workflow.model_profiles, ensure_ascii=False, indent=2, default=_json_default))
    print("\n=== Judge Challenges ===")
    print(json.dumps(result.challenges, ensure_ascii=False, indent=2, default=_json_default))
    print("\n=== Final Reviewed Report ===")
    print(result.final_report)
    print("\n=== Review ===")
    print(json.dumps(result.review, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
