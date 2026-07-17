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
    anchor_inputs: tuple[str, ...]
    required_inputs: tuple[str, ...]
    priority: int = 0


@dataclass(frozen=True)
class BayesianModelRun:
    model_id: str
    version: str
    calibration_status: str
    parameter_hash: str
    group_key: str
    anchor_claim_id: str
    input_claim_ids: list[str]
    soft_evidence: dict[str, float]
    soft_evidence_sources: dict[str, list[str]]
    node_values: dict[str, float]
    derived_values: dict[str, float]


@dataclass(frozen=True)
class BayesianAbstention:
    model_id: str
    reason: str
    group_key: str = ""
    anchor_claim_id: str = ""
    missing_inputs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BayesianToolResult:
    selected_model_ids: list[str] = field(default_factory=list)
    skipped_model_ids: list[str] = field(default_factory=list)
    runs: list[BayesianModelRun] = field(default_factory=list)
    abstentions: list[BayesianAbstention] = field(default_factory=list)


class BayesianModelRegistry:
    def __init__(self, registry_path: str | Path = DEFAULT_REGISTRY_PATH):
        self.path = Path(registry_path)
        self.version, self.models = self._load()

    def select(
        self,
        case_domains: list[str],
        claims: list[EvidenceClaim],
    ) -> list[RegisteredBayesianModel]:
        del case_domains
        predicates = {claim.behavior_type for claim in claims}
        selected = []
        for model in self.models:
            if not predicates.intersection(model.trigger_predicates):
                continue
            anchor_predicates = {
                predicate
                for predicate, input_id in model.input_map.items()
                if input_id in model.anchor_inputs
            }
            if anchor_predicates and not predicates.intersection(anchor_predicates):
                continue
            selected.append(model)
        return selected

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
            _validate_registered_model(model)
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
            return BayesianToolResult(
                skipped_model_ids=[model.model_id for model in self.registry.models],
                abstentions=[
                    BayesianAbstention(
                        model_id="registry",
                        reason="no_matching_relation_component",
                    )
                ] if claims else [],
            )

        assessments = {item.claim_id: item for item in claim_assessments}
        runs: list[BayesianModelRun] = []
        abstentions: list[BayesianAbstention] = []
        for model in selected:
            model_runs, model_abstentions = self._run_model(model, claims, assessments)
            runs.extend(model_runs)
            abstentions.extend(model_abstentions)
        return BayesianToolResult(
            selected_model_ids=[model.model_id for model in selected],
            skipped_model_ids=[
                model.model_id for model in self.registry.models if model not in selected
            ],
            runs=runs,
            abstentions=abstentions,
        )

    def _run_model(
        self,
        model: RegisteredBayesianModel,
        claims: list[EvidenceClaim],
        assessments: Mapping[str, ClaimAssessment],
    ) -> tuple[list[BayesianModelRun], list[BayesianAbstention]]:
        if not model.path.is_file():
            raise ModelValidationError(f"model file does not exist: {model.path}")

        anchor_claims = [
            claim
            for claim in claims
            if model.input_map.get(claim.behavior_type) in model.anchor_inputs
            and _claim_has_allegation_anchor(claim, assessments.get(claim.claim_id))
        ]
        if not anchor_claims:
            return [], [
                BayesianAbstention(
                    model_id=model.model_id,
                    reason="missing_allegation_anchor",
                )
            ]
        grouped: dict[str, tuple[EvidenceClaim, list[EvidenceClaim]]] = {}
        for anchor in anchor_claims:
            key = _claim_group_key(anchor)
            if key in grouped:
                continue
            grouped[key] = (anchor, [])
            for claim in claims:
                if _claims_compatible(anchor, claim, model, anchor_claims):
                    grouped[key][1].append(claim)
        runs: list[BayesianModelRun] = []
        abstentions: list[BayesianAbstention] = []
        for group_key, (anchor, group) in grouped.items():
            run, abstention = self._run_group(model, group_key, anchor, group, assessments)
            if run is not None:
                runs.append(run)
            if abstention is not None:
                abstentions.append(abstention)
        return runs, abstentions

    def _run_group(
        self,
        model: RegisteredBayesianModel,
        group_key: str,
        anchor: EvidenceClaim,
        claims: list[EvidenceClaim],
        assessments: Mapping[str, ClaimAssessment],
    ) -> tuple[BayesianModelRun | None, BayesianAbstention | None]:

        soft_evidence: dict[str, float] = {}
        soft_evidence_sources: dict[str, list[str]] = {}
        for claim in claims:
            input_node = model.input_map.get(claim.behavior_type)
            value = _assessment_support(assessments.get(claim.claim_id))
            if input_node is None or value is None:
                continue
            current = soft_evidence.get(input_node)
            if current is None or value > current:
                soft_evidence[input_node] = value
                soft_evidence_sources[input_node] = [claim.claim_id]
            elif value == current:
                soft_evidence_sources.setdefault(input_node, []).append(claim.claim_id)

        missing_inputs = sorted(set(model.required_inputs) - set(soft_evidence))
        if missing_inputs:
            return None, BayesianAbstention(
                model_id=model.model_id,
                reason="missing_required_inputs",
                group_key=group_key,
                anchor_claim_id=anchor.claim_id,
                missing_inputs=missing_inputs,
            )

        result = BayesianInferenceEngine(model.path).infer(soft_evidence)
        return BayesianModelRun(
            model_id=result["model_id"],
            version=result["version"],
            calibration_status=result["calibration_status"],
            parameter_hash=result["parameter_hash"],
            group_key=group_key,
            anchor_claim_id=anchor.claim_id,
            input_claim_ids=list(
                dict.fromkeys(
                    claim_id
                    for claim_ids in soft_evidence_sources.values()
                    for claim_id in claim_ids
                )
            ),
            soft_evidence=soft_evidence,
            soft_evidence_sources=soft_evidence_sources,
            node_values=dict(result["node_values"]),
            derived_values={
                node_id: result["node_values"][node_id]
                for node_id in model.derived_nodes
                if node_id in result["node_values"]
            },
        ), None


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
    if "anchor_inputs" in item and not isinstance(item["anchor_inputs"], list):
        raise ModelValidationError("Bayesian registry anchor_inputs must be a list")
    if "required_inputs" in item and not isinstance(item["required_inputs"], list):
        raise ModelValidationError("Bayesian registry required_inputs must be a list")
    priority = item.get("priority", 0)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ModelValidationError("Bayesian registry priority must be integer 0")
    return RegisteredBayesianModel(
        model_id=str(item["model_id"]),
        path=(base_dir / str(item["path"])).resolve(),
        domains=tuple(str(value) for value in item["domains"]),
        trigger_predicates=tuple(str(value) for value in item["trigger_predicates"]),
        input_map={str(key): str(value) for key, value in item["input_map"].items()},
        derived_nodes=tuple(str(value) for value in item["derived_nodes"]),
        anchor_inputs=tuple(
            str(value)
            for value in item.get(
                "anchor_inputs",
                list(dict.fromkeys(str(value) for value in item["input_map"].values()))[:1],
            )
        ),
        required_inputs=tuple(
            str(value)
            for value in item.get(
                "required_inputs",
                item.get(
                    "anchor_inputs",
                    list(dict.fromkeys(str(value) for value in item["input_map"].values()))[:1],
                ),
            )
        ),
        priority=priority,
    )


def _validate_registered_model(model: RegisteredBayesianModel) -> None:
    if not model.path.is_file():
        raise ModelValidationError(f"model file does not exist: {model.path}")
    result = BayesianInferenceEngine(model.path).infer({})
    if result["model_id"] != model.model_id:
        raise ModelValidationError(
            f"registry model_id {model.model_id} does not match model file {result['model_id']}"
        )
    node_ids = set(result["node_values"])
    missing_inputs = set(model.input_map.values()) - node_ids
    missing_outputs = set(model.derived_nodes) - node_ids
    missing_anchors = set(model.anchor_inputs) - node_ids
    missing_required = set(model.required_inputs) - node_ids
    if missing_inputs:
        raise ModelValidationError(
            f"registry input_map references unknown nodes: {sorted(missing_inputs)}"
        )
    if missing_outputs:
        raise ModelValidationError(
            f"registry derived_nodes references unknown nodes: {sorted(missing_outputs)}"
        )
    if missing_anchors:
        raise ModelValidationError(
            f"registry anchor_inputs references unknown nodes: {sorted(missing_anchors)}"
        )
    if missing_required:
        raise ModelValidationError(
            f"registry required_inputs references unknown nodes: {sorted(missing_required)}"
        )


def _assessment_support(assessment: ClaimAssessment | None) -> float | None:
    if assessment is None:
        return None
    if assessment.opinion is None:
        return (
            min(1.0, max(0.0, float(assessment.support_index)))
            if assessment.support_index
            else None
        )
    if (
        assessment.opinion.support == 0
        and assessment.opinion.opposition == 0
        and assessment.opinion.uncertainty >= 1
    ):
        return None
    if assessment.support_index:
        return min(1.0, max(0.0, float(assessment.support_index)))
    return min(
        1.0,
        max(
            0.0,
            float(assessment.opinion.support)
            + 0.5 * float(assessment.opinion.uncertainty),
        ),
    )


def _claim_group_key(claim: EvidenceClaim) -> str:
    target = claim.target_person or claim.object or "unknown-target"
    event = claim.event_id or f"unknown-event:{claim.claim_id}"
    return "|".join((event, claim.subject or "unknown-actor", target))


def _claims_compatible(
    anchor: EvidenceClaim,
    candidate: EvidenceClaim,
    model: RegisteredBayesianModel,
    anchor_claims: list[EvidenceClaim] | None = None,
) -> bool:
    # Missing event identifiers are treated as unscoped evidence. They may join a
    # uniquely identified actor/target group, while two explicit different events
    # must never be fused.
    anchor_event = "" if _is_material_scope(anchor.event_id) else anchor.event_id
    candidate_event = "" if _is_material_scope(candidate.event_id) else candidate.event_id
    if anchor_event and candidate_event and candidate_event != anchor_event:
        return False
    if not anchor_event and not candidate_event and candidate.claim_id != anchor.claim_id:
        return False
    if anchor_event and not candidate_event and anchor_claims:
        compatible_events = {
            other.event_id
            for other in anchor_claims
            if other.event_id
            and not _is_material_scope(other.event_id)
            and _same_anchor_entities(anchor, other)
        }
        if len(compatible_events) != 1:
            return False
    candidate_input = model.input_map.get(candidate.behavior_type)
    if candidate_input in model.anchor_inputs and candidate.subject != anchor.subject:
        return False
    anchor_target = anchor.target_person or anchor.object
    candidate_target = candidate.target_person or candidate.object
    anchor_entities = {value for value in (anchor.subject, anchor.target_person, anchor.object) if value}
    candidate_entities = {
        value for value in (candidate.subject, candidate.target_person, candidate.object) if value
    }
    same_relation_entities = len(anchor_entities & candidate_entities) >= 2
    if (
        anchor_target
        and candidate_target
        and candidate_target != anchor_target
        and not same_relation_entities
    ):
        return False
    if anchor_target and not candidate_target and candidate.subject not in {
        anchor.subject,
        anchor_target,
    }:
        return False
    return not anchor_entities or not candidate_entities or bool(anchor_entities & candidate_entities)


def _is_material_scope(event_id: str) -> bool:
    return event_id.startswith("MATERIAL-")


def _same_anchor_entities(left: EvidenceClaim, right: EvidenceClaim) -> bool:
    return (
        left.subject == right.subject
        and (left.target_person or left.object) == (right.target_person or right.object)
    )


def _claim_has_allegation_anchor(
    claim: EvidenceClaim,
    assessment: ClaimAssessment | None,
) -> bool:
    roles = claim.metadata.get("assertion_roles")
    if roles is not None:
        return bool(
            {"allegation", "statement_evidence", "evidence_observation"}
            & set(roles)
        ) and _assessment_has_positive_support(assessment)
    # Compatibility for direct callers created before Assertion roles existed.
    return _assessment_has_positive_support(assessment)


def _assessment_has_positive_support(assessment: ClaimAssessment | None) -> bool:
    return bool(
        assessment is not None
        and assessment.opinion is not None
        and float(assessment.opinion.support) > 0.0
    )
