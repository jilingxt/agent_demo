"""Small, auditable evaluator for versioned Bayesian-style model specifications."""

from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


class ModelValidationError(ValueError):
    """Raised when a Bayesian model specification is invalid."""


class BayesianInferenceEngine:
    """Evaluate prior, logistic, and noisy-OR nodes from a supplied model."""

    def __init__(self, model_path: str | Path | None = None, *, model_spec: Mapping[str, Any] | None = None):
        if model_path is not None and model_spec is not None:
            raise ModelValidationError("provide either model_path or model_spec, not both")

        self._model: dict[str, Any] | None = None
        self._node_by_id: dict[str, dict[str, Any]] = {}
        self._ordered_node_ids: list[str] = []
        self._parameter_hash: str | None = None

        if model_path is not None:
            self.load_model(model_path)
        elif model_spec is not None:
            self.load_spec(model_spec)

    def load_model(self, model_path: str | Path) -> None:
        """Load and validate a JSON model file explicitly selected by the caller."""
        try:
            model_spec = json.loads(Path(model_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelValidationError(f"unable to load model: {exc}") from exc
        self.load_spec(model_spec)

    def load_spec(self, model_spec: Mapping[str, Any]) -> None:
        """Load and validate an in-memory model specification."""
        if not isinstance(model_spec, Mapping):
            raise ModelValidationError("model specification must be an object")

        try:
            model = json.loads(json.dumps(model_spec))
        except (TypeError, ValueError) as exc:
            raise ModelValidationError("model specification must be JSON serializable") from exc

        node_by_id, ordered_node_ids = _validate_model(model)
        canonical = json.dumps(_normalized_parameter_model(model), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        self._model = model
        self._node_by_id = node_by_id
        self._ordered_node_ids = ordered_node_ids
        self._parameter_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def infer(self, soft_evidence: Mapping[str, float] | None = None) -> dict[str, Any]:
        """Evaluate the loaded model with optional node-level soft evidence."""
        if self._model is None or self._parameter_hash is None:
            raise ModelValidationError("a model must be loaded before inference")

        evidence = dict(soft_evidence or {})
        for node_id, value in evidence.items():
            if node_id not in self._node_by_id:
                raise ModelValidationError(f"soft evidence references unknown node: {node_id}")
            _validate_probability(value, f"soft evidence for {node_id}")

        values: dict[str, float] = {}
        for node_id in self._ordered_node_ids:
            if node_id in evidence:
                values[node_id] = float(evidence[node_id])
                continue
            node = self._node_by_id[node_id]
            values[node_id] = _evaluate_node(node, values)

        return {
            "node_values": values,
            "model_id": self._model["model_id"],
            "version": self._model["version"],
            "calibration_status": self._model["calibration_status"],
            "parameter_hash": self._parameter_hash,
        }


def _validate_model(model: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    for field in ("model_id", "version", "calibration_status"):
        if not isinstance(model.get(field), str) or not model[field].strip():
            raise ModelValidationError(f"{field} must be a non-empty string")

    nodes = model.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ModelValidationError("nodes must be a non-empty list")

    node_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise ModelValidationError("each node must be an object")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ModelValidationError("each node id must be a non-empty string")
        if node_id in node_by_id:
            raise ModelValidationError(f"duplicate node id: {node_id}")
        node_by_id[node_id] = node

    children: dict[str, list[str]] = {node_id: [] for node_id in node_by_id}
    incoming_counts: dict[str, int] = {node_id: 0 for node_id in node_by_id}
    for node_id, node in node_by_id.items():
        _validate_node(node)
        for parent_id in node.get("parents", []):
            if parent_id not in node_by_id:
                raise ModelValidationError(f"node {node_id} references unknown parent: {parent_id}")
            children[parent_id].append(node_id)
            incoming_counts[node_id] += 1

    ordered_node_ids = _topological_order(nodes, children, incoming_counts)
    return node_by_id, ordered_node_ids


def _validate_node(node: dict[str, Any]) -> None:
    node_type = node.get("type")
    if node_type not in {"prior", "logistic", "noisy_or"}:
        raise ModelValidationError(f"unsupported node type: {node_type}")

    required_keys = {
        "prior": {"id", "type", "prior"},
        "logistic": {"id", "type", "parents", "intercept", "weights"},
        "noisy_or": {"id", "type", "parents", "weights"},
    }[node_type]
    allowed_keys = required_keys | ({"leak"} if node_type == "noisy_or" else set())
    missing_keys = required_keys - set(node)
    unexpected_keys = set(node) - allowed_keys
    if missing_keys:
        raise ModelValidationError(f"node {node['id']} is missing required keys: {sorted(missing_keys)}")
    if unexpected_keys:
        raise ModelValidationError(f"node {node['id']} has unsupported keys: {sorted(unexpected_keys)}")

    parents = node.get("parents", [])
    if not isinstance(parents, list) or any(not isinstance(parent, str) or not parent for parent in parents):
        raise ModelValidationError(f"node {node['id']} parents must be a list of node ids")
    if len(parents) != len(set(parents)):
        raise ModelValidationError(f"node {node['id']} has duplicate parents")

    if node_type == "prior":
        if parents:
            raise ModelValidationError(f"prior node {node['id']} cannot have parents")
        _validate_probability(node.get("prior"), f"prior for {node['id']}")
        return

    weights = node.get("weights")
    if not isinstance(weights, dict) or set(weights) != set(parents):
        raise ModelValidationError(f"node {node['id']} weights must match its parents")

    if node_type == "logistic":
        _validate_number(node.get("intercept"), f"intercept for {node['id']}")
        for parent_id, weight in weights.items():
            _validate_number(weight, f"weight for {node['id']}.{parent_id}")
    else:
        _validate_probability(node.get("leak", 0.0), f"leak for {node['id']}")
        for parent_id, weight in weights.items():
            _validate_probability(weight, f"weight for {node['id']}.{parent_id}")


def _normalized_parameter_model(model: Mapping[str, Any]) -> dict[str, Any]:
    normalized_nodes = []
    for node in model["nodes"]:
        normalized_node = {"id": node["id"], "type": node["type"]}
        if node["type"] == "prior":
            normalized_node["prior"] = _normalized_number(node["prior"])
        else:
            parents = sorted(node["parents"])
            normalized_node["parents"] = parents
            normalized_node["weights"] = {
                parent_id: _normalized_number(node["weights"][parent_id]) for parent_id in parents
            }
            if node["type"] == "logistic":
                normalized_node["intercept"] = _normalized_number(node["intercept"])
            else:
                normalized_node["leak"] = _normalized_number(node.get("leak", 0.0))
        normalized_nodes.append(normalized_node)

    return {
        "model_id": model["model_id"],
        "version": model["version"],
        "calibration_status": model["calibration_status"],
        "nodes": sorted(normalized_nodes, key=lambda node: node["id"]),
    }


def _normalized_number(value: int | float) -> str:
    number = Decimal(str(value)).normalize()
    if number == 0:
        return "0"
    return format(number, "f")


def _topological_order(
    nodes: list[dict[str, Any]], children: dict[str, list[str]], incoming_counts: dict[str, int]
) -> list[str]:
    pending = dict(incoming_counts)
    ready = deque(node["id"] for node in nodes if pending[node["id"]] == 0)
    ordered: list[str] = []
    while ready:
        node_id = ready.popleft()
        ordered.append(node_id)
        for child_id in children[node_id]:
            pending[child_id] -= 1
            if pending[child_id] == 0:
                ready.append(child_id)

    if len(ordered) != len(nodes):
        raise ModelValidationError("model graph must be acyclic")
    return ordered


def _evaluate_node(node: Mapping[str, Any], values: Mapping[str, float]) -> float:
    node_type = node["type"]
    if node_type == "prior":
        return float(node["prior"])
    if node_type == "logistic":
        score = float(node["intercept"])
        score += sum(float(node["weights"][parent_id]) * values[parent_id] for parent_id in node["parents"])
        return _sigmoid(score)

    missed_probability = 1.0 - float(node.get("leak", 0.0))
    for parent_id in node["parents"]:
        missed_probability *= 1.0 - float(node["weights"][parent_id]) * values[parent_id]
    return 1.0 - missed_probability


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _validate_number(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ModelValidationError(f"{name} must be a finite number")


def _validate_probability(value: Any, name: str) -> None:
    _validate_number(value, name)
    if not 0.0 <= float(value) <= 1.0:
        raise ModelValidationError(f"{name} must be within [0, 1]")
