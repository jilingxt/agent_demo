"""Adapters from case-agent runtime objects to a portable visualization snapshot."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from case_agent_demo.bayesian_engine import BayesianInferenceEngine
from case_agent_demo.bayesian_tool import BayesianModelRegistry, DEFAULT_REGISTRY_PATH


SNAPSHOT_SCHEMA_VERSION = "1.0"


def build_snapshot(result: Any, registry_path: str | Path | None = None) -> dict[str, Any]:
    """Build a browser-safe snapshot from a WorkflowResult-like object."""
    graph = getattr(result, "evidence_graph", None) or getattr(result, "case_graph", None)
    if graph is None:
        raise ValueError("result must expose evidence_graph or case_graph")

    assertions = list(getattr(result, "assertions", []) or [])
    assessments = list(getattr(result, "claim_assessments", []) or [])
    validation_issues = list(getattr(result, "validation_issues", []) or [])
    assessment_by_claim = {
        str(getattr(item, "claim_id", "")): item for item in assessments
    }

    evidence_nodes, evidence_edges = _evidence_elements(
        graph,
        assertions,
        assessment_by_claim,
        validation_issues,
    )
    bayesian_runs = _bayesian_runs(
        getattr(result, "bayesian_result", None),
        Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH,
    )
    review = _plain(getattr(result, "review", None))
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "confirmed_case_type": str(getattr(result, "confirmed_case_type", "")),
            "executed_agents": list(getattr(result, "executed_agents", []) or []),
            "review": review,
            "reasoning_trace": _plain(getattr(result, "reasoning_trace", {}) or {}),
            "model_versions": _plain(getattr(result, "model_versions", {}) or {}),
        },
        "evidence": {
            "nodes": evidence_nodes,
            "edges": evidence_edges,
            "counts": _evidence_counts(evidence_nodes, evidence_edges),
        },
        "bayesian": {
            "runs": bayesian_runs,
            "count": len(bayesian_runs),
        },
    }
    return snapshot


def save_snapshot(snapshot: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_snapshot(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    snapshot = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(snapshot, dict):
        raise ValueError("visualization snapshot must be a JSON object")
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported snapshot schema: {snapshot.get('schema_version')!r}"
        )
    if not isinstance(snapshot.get("evidence"), dict):
        raise ValueError("visualization snapshot is missing evidence data")
    if not isinstance(snapshot.get("bayesian"), dict):
        raise ValueError("visualization snapshot is missing Bayesian data")
    return snapshot


def _evidence_elements(
    graph: Any,
    assertions: list[Any],
    assessment_by_claim: Mapping[str, Any],
    validation_issues: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    known_ids: set[str] = set()

    for node in getattr(graph, "nodes", []) or []:
        raw_id = str(getattr(node, "node_id", ""))
        ui_id = _ui_id("evidence", raw_id)
        kind = str(getattr(node, "node_type", "fact"))
        details = _plain(node)
        nodes.append(
            _visual_node(
                ui_id,
                raw_id,
                _label(getattr(node, "summary", "") or getattr(node, "behavior", "") or raw_id),
                kind,
                str(getattr(node, "source_type", "")),
                float(getattr(node, "confidence", 0.0) or 0.0),
                details,
            )
        )
        known_ids.add(ui_id)

    for edge in getattr(graph, "edges", []) or []:
        source = _ui_id("evidence", str(getattr(edge, "source_node_id", "")))
        target = _ui_id("evidence", str(getattr(edge, "target_node_id", "")))
        if source not in known_ids or target not in known_ids:
            continue
        raw_id = str(getattr(edge, "edge_id", ""))
        edges.append(
            _visual_edge(
                _ui_id("edge", raw_id),
                source,
                target,
                str(getattr(edge, "edge_type", "related")),
                _plain(edge),
            )
        )

    assertion_by_id: dict[str, Any] = {}
    for assertion in assertions:
        raw_id = str(getattr(assertion, "assertion_id", ""))
        assertion_by_id[raw_id] = assertion
        ui_id = _ui_id("assertion", raw_id)
        details = _plain(assertion)
        nodes.append(
            _visual_node(
                ui_id,
                raw_id,
                _label(f"{getattr(assertion, 'predicate', 'assertion')} · {getattr(assertion, 'stance', '')}"),
                "assertion",
                str(getattr(assertion, "predicate", "")),
                float(details.get("metadata", {}).get("extraction_quality", 0.0) or 0.0),
                details,
            )
        )
        known_ids.add(ui_id)
        source = _ui_id("evidence", str(getattr(assertion, "node_id", "")))
        if source in known_ids:
            edges.append(
                _visual_edge(
                    _ui_id("edge", f"{raw_id}:asserts"),
                    source,
                    ui_id,
                    "asserts",
                    {"assertion_id": raw_id},
                )
            )

    claims = list(getattr(graph, "claims", []) or [])
    for claim in claims:
        raw_id = str(getattr(claim, "claim_id", ""))
        assessment = assessment_by_claim.get(raw_id)
        status = str(getattr(assessment, "status", getattr(claim, "status", "")))
        kind = "derived_claim" if status == "bayesian_derived" else "claim"
        details = _plain(claim)
        if assessment is not None:
            details["assessment"] = _plain(assessment)
        ui_id = _ui_id("claim", raw_id)
        score = float(
            getattr(assessment, "support_index", 0.0)
            if assessment is not None
            else (details.get("confidence_profile") or {}).get("final_score", 0.0)
            or 0.0
        )
        nodes.append(
            _visual_node(
                ui_id,
                raw_id,
                _label(f"{getattr(claim, 'behavior_type', 'claim')} · {getattr(claim, 'subject', '')}"),
                kind,
                status,
                score,
                details,
            )
        )
        known_ids.add(ui_id)

    claim_by_id = {str(getattr(claim, "claim_id", "")): claim for claim in claims}
    for claim_id, claim in claim_by_id.items():
        target = _ui_id("claim", claim_id)
        for assertion_id in getattr(claim, "assertion_ids", []) or []:
            assertion = assertion_by_id.get(str(assertion_id))
            if assertion is None:
                continue
            source = _ui_id("assertion", str(assertion_id))
            stance = str(getattr(assertion, "stance", "ambiguous"))
            relation = {
                "affirm": "supports_claim",
                "deny": "opposes_claim",
            }.get(stance, "ambiguous_claim")
            edges.append(
                _visual_edge(
                    _ui_id("edge", f"{assertion_id}:{claim_id}"),
                    source,
                    target,
                    relation,
                    {"stance": stance},
                )
            )
        metadata = getattr(claim, "metadata", {}) or {}
        for input_claim_id in metadata.get("input_claim_ids", []) or []:
            source = _ui_id("claim", str(input_claim_id))
            if source in known_ids:
                edges.append(
                    _visual_edge(
                        _ui_id("edge", f"{input_claim_id}:{claim_id}:bayesian"),
                        source,
                        target,
                        "bayesian_input",
                        {"derived_by": metadata.get("derived_by", "")},
                    )
                )

    for issue in validation_issues:
        raw_id = str(getattr(issue, "issue_id", ""))
        ui_id = _ui_id("issue", raw_id)
        details = _plain(issue)
        nodes.append(
            _visual_node(
                ui_id,
                raw_id,
                _label(getattr(issue, "issue_type", "validation_issue")),
                "validation_issue",
                str(getattr(issue, "severity", "")),
                0.0,
                details,
            )
        )
        known_ids.add(ui_id)
        targets = [
            *[_ui_id("claim", str(value)) for value in getattr(issue, "target_claim_ids", []) or []],
            *[_ui_id("evidence", str(value)) for value in getattr(issue, "target_node_ids", []) or []],
        ]
        for index, source in enumerate(targets):
            if source not in known_ids:
                continue
            edges.append(
                _visual_edge(
                    _ui_id("edge", f"{raw_id}:target:{index}"),
                    source,
                    ui_id,
                    "raises_issue",
                    {"issue_id": raw_id},
                )
            )

    return nodes, edges


def _bayesian_runs(
    bayesian_result: Any,
    registry_path: Path,
) -> list[dict[str, Any]]:
    if not isinstance(bayesian_result, Mapping):
        return []
    raw_runs = bayesian_result.get("runs")
    if not isinstance(raw_runs, list):
        return []

    registry = BayesianModelRegistry(registry_path)
    registered = {model.model_id: model for model in registry.models}
    runs: list[dict[str, Any]] = []
    for index, raw_run in enumerate(raw_runs):
        if not isinstance(raw_run, Mapping):
            continue
        model_id = str(raw_run.get("model_id", ""))
        model = registered.get(model_id)
        spec = _load_model_spec(model.path) if model is not None else None
        run = _bayesian_run(index, raw_run, spec, model)
        runs.append(run)
    return runs


def _bayesian_run(index: int, raw_run: Mapping[str, Any], spec: dict[str, Any] | None, model: Any) -> dict[str, Any]:
    model_id = str(raw_run.get("model_id", "unknown-model"))
    group_key = str(raw_run.get("group_key", f"run-{index + 1}"))
    run_id = f"{model_id}:{group_key}"
    node_values = {
        str(key): float(value)
        for key, value in (raw_run.get("node_values") or {}).items()
    }
    soft_evidence = {
        str(key): float(value)
        for key, value in (raw_run.get("soft_evidence") or {}).items()
    }
    source_map = {
        str(key): [str(item) for item in value]
        for key, value in (raw_run.get("soft_evidence_sources") or {}).items()
        if isinstance(value, list)
    }
    derived_nodes = set(getattr(model, "derived_nodes", ()) or ())
    input_nodes = set(getattr(model, "input_map", {}).values()) if model is not None else set(soft_evidence)
    anchor_inputs = set(getattr(model, "anchor_inputs", ()) or ())

    spec_nodes = list((spec or {}).get("nodes", []))
    spec_by_id = {str(node.get("id", "")): node for node in spec_nodes if isinstance(node, dict)}
    ordered_ids = list(node_values)
    for node_id in spec_by_id:
        if node_id not in ordered_ids:
            ordered_ids.append(node_id)
    baseline_values = (
        BayesianInferenceEngine(model_spec=spec).infer({})["node_values"]
        if spec is not None
        else {}
    )

    nodes = []
    for node_id in ordered_ids:
        node_spec = spec_by_id.get(node_id, {"id": node_id, "type": "unknown"})
        value = node_values.get(node_id, float(baseline_values.get(node_id, 0.0)))
        role = "derived" if node_id in derived_nodes else "input" if node_id in input_nodes else "intermediate"
        nodes.append(
            {
                "id": node_id,
                "label": node_id,
                "type": str(node_spec.get("type", "unknown")),
                "role": role,
                "value": round(value, 6),
                "baseline_value": round(float(baseline_values.get(node_id, value)), 6),
                "observed": node_id in soft_evidence,
                "soft_evidence": soft_evidence.get(node_id),
                "source_claim_ids": source_map.get(node_id, []),
                "is_anchor": node_id in anchor_inputs,
                "parents": [str(item) for item in node_spec.get("parents", [])],
                "parameters": _node_parameters(node_spec),
                "calculation": _node_calculation(node_spec, node_values),
            }
        )

    edges = []
    for node in spec_nodes:
        if not isinstance(node, dict):
            continue
        weights = node.get("weights") if isinstance(node.get("weights"), dict) else {}
        for parent in node.get("parents", []) or []:
            edges.append(
                {
                    "id": f"{parent}:{node.get('id')}",
                    "source": str(parent),
                    "target": str(node.get("id", "")),
                    "weight": float(weights.get(parent, 0.0)),
                }
            )

    return {
        "id": run_id,
        "label": f"{model_id} · {group_key}",
        "model_id": model_id,
        "version": str(raw_run.get("version", "")),
        "calibration_status": str(raw_run.get("calibration_status", "")),
        "parameter_hash": str(raw_run.get("parameter_hash", "")),
        "group_key": group_key,
        "anchor_claim_id": str(raw_run.get("anchor_claim_id", "")),
        "input_claim_ids": [str(item) for item in raw_run.get("input_claim_ids", []) or []],
        "derived_nodes": sorted(derived_nodes),
        "input_nodes": sorted(input_nodes),
        "nodes": nodes,
        "edges": edges,
        "spec": _plain(spec or {"model_id": model_id, "nodes": []}),
    }


def _node_parameters(node: Mapping[str, Any]) -> dict[str, Any]:
    node_type = node.get("type")
    if node_type == "prior":
        return {"prior": node.get("prior")}
    if node_type == "logistic":
        return {
            "intercept": node.get("intercept"),
            "weights": _plain(node.get("weights", {})),
        }
    if node_type == "noisy_or":
        return {
            "leak": node.get("leak", 0.0),
            "weights": _plain(node.get("weights", {})),
        }
    return {}


def _node_calculation(node: Mapping[str, Any], values: Mapping[str, float]) -> dict[str, Any]:
    node_type = node.get("type")
    if node_type == "prior":
        return {"formula": "prior", "prior": node.get("prior")}
    parents = [str(item) for item in node.get("parents", []) or []]
    weights = node.get("weights") if isinstance(node.get("weights"), Mapping) else {}
    if node_type == "logistic":
        terms = [
            {
                "parent": parent,
                "value": round(float(values.get(parent, 0.0)), 6),
                "weight": float(weights.get(parent, 0.0)),
                "contribution": round(float(values.get(parent, 0.0)) * float(weights.get(parent, 0.0)), 6),
            }
            for parent in parents
        ]
        raw_score = float(node.get("intercept", 0.0)) + sum(item["contribution"] for item in terms)
        return {
            "formula": "sigmoid(intercept + Σ weight × parent)",
            "intercept": float(node.get("intercept", 0.0)),
            "terms": terms,
            "raw_score": round(raw_score, 6),
        }
    if node_type == "noisy_or":
        terms = [
            {
                "parent": parent,
                "value": round(float(values.get(parent, 0.0)), 6),
                "weight": float(weights.get(parent, 0.0)),
                "miss_factor": round(1.0 - float(weights.get(parent, 0.0)) * float(values.get(parent, 0.0)), 6),
            }
            for parent in parents
        ]
        return {
            "formula": "1 - (1 - leak) × Π(1 - weight × parent)",
            "leak": float(node.get("leak", 0.0)),
            "terms": terms,
        }
    return {"formula": "unknown"}


def _load_model_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _visual_node(
    node_id: str,
    raw_id: str,
    label: str,
    kind: str,
    subkind: str,
    score: float,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": node_id,
        "raw_id": raw_id,
        "label": label,
        "kind": kind,
        "subkind": subkind,
        "score": round(score, 6),
        "details": details,
    }


def _visual_edge(
    edge_id: str,
    source: str,
    target: str,
    relation: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "label": relation,
        "details": details,
    }


def _evidence_counts(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    for node in nodes:
        kind = str(node.get("kind", "unknown"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"nodes": len(nodes), "edges": len(edges), "by_kind": kinds}


def _plain(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _ui_id(namespace: str, raw_id: str) -> str:
    return f"{namespace}:{raw_id}"


def _label(value: Any, limit: int = 42) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text or "未命名节点"
    return text[: limit - 1] + "…"
