"""Case-neutral, registry-driven Bayesian evidence inference Tool."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from case_agent_demo.bayesian_engine import BayesianInferenceEngine, ModelValidationError
from case_agent_demo.models import ClaimAssessment, EvidenceClaim


DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "bayesian_models"
    / "registry.json"
)


@dataclass(frozen=True)
class RegisteredBayesianModel:
    model_id: str
    path: Path
    domains: tuple[str, ...]
    trigger_predicates: tuple[str, ...]
    input_map: Mapping[str, str]
    derived_nodes: tuple[str, ...]
    priority: int = 0


@dataclass(frozen=True)
class BayesianModelRun:
    model_id: str
    version: str
    calibration_status: str
    parameter_hash: str
    input_claim_ids: list[str]
    soft_evidence: dict[str, float]
    derived_values: dict[str, float]


@dataclass(frozen=True)
class BayesianToolResult:
    selected_model_ids: list[str] = field(default_factory=list)
    runs: list[BayesianModelRun] = field(default_factory=list)


class BayesianModelRegistry:
    def __init__(self, registry_path: str | Path = DEFAULT_REGISTRY_PATH):
        self.path = Path(registry_path)
        self.version, self.models = self._load()

    def select(
        self,
        case_domains: list[str],
        claims: list[EvidenceClaim],
    ) -> list[RegisteredBayesianModel]:
        domains = set(case_domains)
        predicates = {claim.behavior_type for claim in claims}
        return [
            model
            for model in self.models
            if domains.intersection(model.domains)
            or predicates.intersection(model.trigger_predicates)
        ]

    def _load(self) -> tuple[str, list[RegisteredBayesianModel]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelValidationError(f"unable to load Bayesian registry: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise ModelValidationError("Bayesian registry models must be a list")

        models: list[RegisteredBayesianModel] = []
        seen: set[str] = set()
        for item in data["models"]:
            model = _registered_model(item, self.path.parent)
            if model.priority != 0:
                raise ModelValidationError("all Bayesian models must have equal priority 0")
            if model.model_id in seen:
                raise ModelValidationError(f"duplicate Bayesian registry model: {model.model_id}")
            seen.add(model.model_id)
            models.append(model)
        return str(data.get("version", "1")), models


class BayesianEvidenceTool:
    def __init__(self, registry: BayesianModelRegistry | None = None):
        self.registry = registry or BayesianModelRegistry()

    def evaluate(
        self,
        case_domains: list[str],
        claims: list[EvidenceClaim],
        claim_assessments: list[ClaimAssessment],
    ) -> BayesianToolResult:
        selected = self.registry.select(case_domains, claims)
        if not selected:
            return BayesianToolResult()

        assessments = {item.claim_id: item for item in claim_assessments}
        runs = [self._run(model, claims, assessments) for model in selected]
        return BayesianToolResult(
            selected_model_ids=[model.model_id for model in selected],
            runs=runs,
        )

    def _run(
        self,
        model: RegisteredBayesianModel,
        claims: list[EvidenceClaim],
        assessments: Mapping[str, ClaimAssessment],
    ) -> BayesianModelRun:
        if not model.path.is_file():
            raise ModelValidationError(f"model file does not exist: {model.path}")

        soft_evidence: dict[str, float] = {}
        input_claim_ids: list[str] = []
        for claim in claims:
            input_node = model.input_map.get(claim.behavior_type)
            assessment = assessments.get(claim.claim_id)
            if input_node is None or assessment is None:
                continue
            value = _assessment_support(assessment)
            if input_node not in soft_evidence or value > soft_evidence[input_node]:
                soft_evidence[input_node] = value
            input_claim_ids.append(claim.claim_id)

        result = BayesianInferenceEngine(model.path).infer(soft_evidence)
        return BayesianModelRun(
            model_id=result["model_id"],
            version=result["version"],
            calibration_status=result["calibration_status"],
            parameter_hash=result["parameter_hash"],
            input_claim_ids=list(dict.fromkeys(input_claim_ids)),
            soft_evidence=soft_evidence,
            derived_values={
                node_id: result["node_values"][node_id]
                for node_id in model.derived_nodes
                if node_id in result["node_values"]
            },
        )


def _registered_model(item: object, base_dir: Path) -> RegisteredBayesianModel:
    if not isinstance(item, dict):
        raise ModelValidationError("each Bayesian registry entry must be an object")
    required = {
        "model_id",
        "path",
        "domains",
        "trigger_predicates",
        "input_map",
        "derived_nodes",
    }
    missing = required - set(item)
    if missing:
        raise ModelValidationError(f"Bayesian registry entry missing fields: {sorted(missing)}")
    if not isinstance(item["input_map"], dict):
        raise ModelValidationError("Bayesian registry input_map must be an object")
    for field_name in ("domains", "trigger_predicates", "derived_nodes"):
        if not isinstance(item[field_name], list):
            raise ModelValidationError(f"Bayesian registry {field_name} must be a list")
    return RegisteredBayesianModel(
        model_id=str(item["model_id"]),
        path=(base_dir / str(item["path"])).resolve(),
        domains=tuple(str(value) for value in item["domains"]),
        trigger_predicates=tuple(str(value) for value in item["trigger_predicates"]),
        input_map={str(key): str(value) for key, value in item["input_map"].items()},
        derived_nodes=tuple(str(value) for value in item["derived_nodes"]),
        priority=int(item.get("priority", 0)),
    )


def _assessment_support(assessment: ClaimAssessment) -> float:
    if assessment.support_index:
        return min(1.0, max(0.0, float(assessment.support_index)))
    if assessment.opinion is None:
        return 0.0
    return min(
        1.0,
        max(
            0.0,
            float(assessment.opinion.support)
            + 0.5 * float(assessment.opinion.uncertainty),
        ),
    )
