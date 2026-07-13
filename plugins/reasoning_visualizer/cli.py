"""Command line entry point for capturing and serving visualization snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import webbrowser

from .server import create_server
from .snapshot import build_snapshot, load_snapshot, save_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Visualize evidence and Bayesian reasoning graphs.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--snapshot", help="Serve an existing visualization snapshot JSON file.")
    source.add_argument("--sample", action="store_true", help="Run the built-in case demo before serving.")
    source.add_argument("--evidence-dir", help="Run the current project against an evidence vault.")
    parser.add_argument("--case-type", help="Human-confirmed case type; required with --evidence-dir.")
    parser.add_argument("--authority-verifications", help="Optional authority-verification JSON file.")
    parser.add_argument("--registry", help="Optional Bayesian registry.json path.")
    parser.add_argument("--enable-qwen-vision", action="store_true", help="Enable Qwen vision for evidence-dir images.")
    parser.add_argument("--export", help="Write the portable visualization snapshot to this JSON file.")
    parser.add_argument("--no-serve", action="store_true", help="Capture/export without starting the viewer.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    parser.add_argument("--port", type=int, default=8765, help="Local viewer port; use 0 for an available port.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.evidence_dir and not args.case_type:
        parser.error("--case-type is required with --evidence-dir")
    if args.no_serve and not args.export:
        parser.error("--no-serve requires --export")

    if args.snapshot:
        snapshot = load_snapshot(args.snapshot)
    else:
        result = _run_current_workflow(args)
        snapshot = build_snapshot(result, registry_path=args.registry)

    if args.export:
        target = save_snapshot(snapshot, args.export)
        print(f"Visualization snapshot: {target.resolve()}")
    if args.no_serve:
        return

    server = create_server(snapshot, port=args.port)
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"Reasoning visualizer: {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _run_current_workflow(args: argparse.Namespace):
    from case_agent_demo.cli import attach_qwen_vision_tool, sample_materials
    from case_agent_demo.config import ModelProfiles
    from case_agent_demo.evidence_intake import EvidenceIntake
    from case_agent_demo.workflow import CaseWorkflow

    materials = (
        EvidenceIntake(args.evidence_dir).load_materials()
        if args.evidence_dir
        else sample_materials()
    )
    case_type = args.case_type or "盗窃类案件"
    workflow = CaseWorkflow(model_profiles=ModelProfiles.from_runtime_config())
    if args.enable_qwen_vision:
        attach_qwen_vision_tool(workflow)
    verifications = None
    if args.authority_verifications:
        verifications = json.loads(
            Path(args.authority_verifications).read_text(encoding="utf-8-sig")
        )
    return workflow.run(
        materials,
        confirmed_case_type=case_type,
        authority_verifications=verifications,
    )
