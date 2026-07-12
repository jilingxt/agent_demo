"""Unified evidence assessment pipeline with registry-driven Bayesian Tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from case_agent_demo.bayesian_tool import (
    BayesianEvidenceTool,
    BayesianModelRegistry,
    BayesianToolResult,
)
from case_agent_demo.domain_affinity import CaseDomainRouter
from case_agent_demo.evidence_reasoning import (
    AssertionNormalizer,
    ClaimBuilderV2,
    SubjectiveEvidenceEngine,
)
from case_agent_demo.models import (
    ClaimAssessment,
    ConfidenceProfile,
    EvidenceAssertion,
    EvidenceClaim,
    EvidenceGraph,
)


_SUBJECTIVE_MODEL_VERSION = "subjective-evidence-v1"
_STATUS_LABELS = {
    "unassessed": "低可信或被冲突削弱",
    "supported": "有一定印证",
    "authority_anchored": "权威材料支持",
    "contested": "争议事实，尚不足以否定",
    "authority_contested": "权威意见存在争议",
    "opposing_dominant": "低可信或被冲突削弱",
    "insufficient": "明显存疑，需补强",
}


@dataclass(frozen=True)
class EvidenceReasoningResult:
    assertions: list[EvidenceAssertion]
    claims: list[EvidenceClaim]
    claim_assessments: list[ClaimAssessment]
    bayesian_result: dict | None = None
    reasoning_trace: dict = field(default_factory=dict)
    model_versions: dict = field(default_factory=dict)


class EvidenceReasoningEngine:
    """Run evidence fusion and all matching equal-priority Bayesian Tools."""

    def __init__(
        self,
        normalizer: AssertionNormalizer | None = None,
        claim_builder: ClaimBuilderV2 | None = None,
        subjective_engine: SubjectiveEvidenceEngine | None = None,
        bayesian_tool: BayesianEvidenceTool | None = None,
        domain_router: CaseDomainRouter | None = None,
        model_dir: str | Path | None = None,
    ):
        self.normalizer = normalizer or AssertionNormalizer()
        self.claim_builder = claim_builder or ClaimBuilderV2(self.normalizer)
        self.subjective_engine = subjective_engine or SubjectiveEvidenceEngine()
        registry = (
            BayesianModelRegistry(Path(model_dir) / "registry.json")
            if model_dir is not None
            else None
        )
        self.bayesian_tool = bayesian_tool or BayesianEvidenceTool(registry)
        self.domain_router = domain_router or CaseDomainRouter()

    def evaluate(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        authority_verifications: Sequence[Mapping] | Mapping[str, Mapping] | None = None,
    ) -> EvidenceReasoningResult:
        assertions = self.normalizer.normalize_graph(evidence_graph)
        assertions = _apply_authority_verifications(assertions, authority_verifications)
        claims = self.claim_builder.build_claims(assertions, evidence_graph)

        assessments: list[ClaimAssessment] = []
        scored_claims: list[EvidenceClaim] = []
        for claim in claims:
            assertion_ids = set(claim.assertion_ids)
            claim_assertions = [
                assertion for assertion in assertions if assertion.assertion_id in assertion_ids
            ]
            assessment = self.subjective_engine.evaluate(claim, claim_assertions)
            opinion = assessment.opinion
            support_index = opinion.support + 0.5 * opinion.uncertainty
            assessment = replace(assessment, support_index=round(support_index, 4))
            assessments.append(assessment)
            scored_claims.append(
                replace(
                    claim,
                    confidence_profile=ConfidenceProfile(
                        corroboration_score=opinion.support,
                        contradiction_score=opinion.opposition,
                        uncertainty=opinion.uncertainty,
                        final_score=round(support_index, 4),
                        label=_STATUS_LABELS.get(assessment.status, assessment.status),
                        reasons=assessment.reasons,
                    ),
                )
            )

        case_domains = [
            affinity.domain_id
            for affinity in self.domain_router.infer_domains(case_type, evidence_graph)
        ]
        tool_result = self.bayesian_tool.evaluate(case_domains, scored_claims, assessments)
        bayesian_result = _tool_result_to_dict(tool_result)
        model_versions: dict[str, object] = {"subjective": _SUBJECTIVE_MODEL_VERSION}
        if bayesian_result is not None:
            bayesian_versions = [
                f"{run.model_id}:{run.version}" for run in tool_result.runs
            ]
            model_versions["bayesian"] = (
                bayesian_versions[0] if len(bayesian_versions) == 1 else "multi_model"
            )
            model_versions["bayesian_models"] = bayesian_versions
            scored_claims, assessments = _append_derived_assessments(
                scored_claims,
                assessments,
                tool_result,
            )

        return EvidenceReasoningResult(
            assertions=assertions,
            claims=scored_claims,
            claim_assessments=assessments,
            bayesian_result=bayesian_result,
            reasoning_trace={
                "assertion_count": len(assertions),
                "claim_count": len(scored_claims),
                "case_domains": case_domains,
                "bayesian_models": model_versions.get("bayesian_models", []),
            },
            model_versions=model_versions,
        )


def _append_derived_assessments(
    claims: list[EvidenceClaim],
    assessments: list[ClaimAssessment],
    tool_result: BayesianToolResult,
) -> tuple[list[EvidenceClaim], list[ClaimAssessment]]:
    by_id = {claim.claim_id: claim for claim in claims}
    derived_claims: list[EvidenceClaim] = []
    derived_assessments: list[ClaimAssessment] = []
    for run in tool_result.runs:
        anchor = by_id.get(run.anchor_claim_id)
        actor = anchor.subject if anchor is not None else ""
        target = (anchor.target_person or anchor.object) if anchor is not None else ""
        event_id = anchor.event_id if anchor is not None else ""
        model_version = f"{run.model_id}:{run.version}"
        for node_id, value in run.derived_values.items():
            claim_id = (
                f"CL-{run.model_id}-{node_id}-{actor or 'unknown'}-"
                f"{target or 'unknown'}-{event_id or 'case'}"
            )
            posterior = round(float(value), 4)
            derived_claims.append(
                EvidenceClaim(
                    claim_id=claim_id,
                    subject=actor,
                    behavior_type=node_id,
                    target_person=target,
                    event_id=event_id,
                    confidence_profile=ConfidenceProfile(
                        final_score=posterior,
                        label="贝叶斯事实派生结果（专家先验，未经历史数据校准）",
                        reasons=["该结果只表达事实要素关系，不是违法犯罪或处罚结论。"],
                    ),
                    metadata={
                        "derived_by": model_version,
                        "input_claim_ids": run.input_claim_ids,
                    },
                )
            )
            derived_assessments.append(
                ClaimAssessment(
                    claim_id=claim_id,
                    status="bayesian_derived",
                    support_index=posterior,
                    bayesian_posterior=posterior,
                    bayesian_model_version=model_version,
                    reasons=[
                        "派生结果由版本化、同级的贝叶斯事实模型生成。",
                        "参数为未经历史数据校准的专家先验，不作为事实概率或最终法律结论。",
                    ],
                )
            )
    return [*claims, *derived_claims], [*assessments, *derived_assessments]


def _tool_result_to_dict(tool_result: BayesianToolResult) -> dict | None:
    if not tool_result.runs:
        return None
    node_values: dict[str, float] = {}
    soft_evidence: dict[str, float] = {}
    soft_evidence_sources: dict[str, list[str]] = {}
    multi_run = len(tool_result.runs) > 1
    model_node_values: dict[str, dict[str, float]] = {}
    model_soft_evidence: dict[str, dict[str, float]] = {}
    for run in tool_result.runs:
        namespace = f"{run.model_id}:{run.group_key}"
        model_node_values[namespace] = dict(run.node_values)
        model_soft_evidence[namespace] = dict(run.soft_evidence)
        for node_id, value in run.derived_values.items():
            key = f"{namespace}:{node_id}" if multi_run else node_id
            node_values[key] = value
        for node_id, value in run.soft_evidence.items():
            key = f"{namespace}:{node_id}" if multi_run else node_id
            soft_evidence[key] = value
        for node_id, claim_ids in run.soft_evidence_sources.items():
            key = f"{namespace}:{node_id}" if multi_run else node_id
            soft_evidence_sources.setdefault(key, []).extend(claim_ids)
    first = tool_result.runs[0]
    calibration_statuses = {
        f"{run.model_id}:{run.group_key}": run.calibration_status for run in tool_result.runs
    }
    parameter_hashes = {
        f"{run.model_id}:{run.group_key}": run.parameter_hash for run in tool_result.runs
    }
    combined_hash = hashlib.sha256(
        json.dumps(parameter_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "selected_model_ids": tool_result.selected_model_ids,
        "skipped_model_ids": tool_result.skipped_model_ids,
        "model_id": first.model_id if len(tool_result.runs) == 1 else "multi_model",
        "version": first.version if len(tool_result.runs) == 1 else "registry-v1",
        "calibration_status": first.calibration_status if not multi_run else "multi_model",
        "calibration_statuses": calibration_statuses,
        "parameter_hash": first.parameter_hash if not multi_run else combined_hash,
        "parameter_hashes": parameter_hashes,
        "node_values": node_values,
        "model_node_values": model_node_values,
        "soft_evidence": soft_evidence,
        "model_soft_evidence": model_soft_evidence,
        "soft_evidence_sources": soft_evidence_sources,
        "runs": [asdict(run) for run in tool_result.runs],
    }


def _apply_authority_verifications(
    assertions: list[EvidenceAssertion],
    verifications: Sequence[Mapping] | Mapping[str, Mapping] | None,
) -> list[EvidenceAssertion]:
    if not verifications:
        return assertions

    if isinstance(verifications, Mapping):
        by_key = {
            str(key): value
            for key, value in verifications.items()
            if isinstance(value, Mapping)
        }
    else:
        by_key = {}
        for value in verifications:
            if not isinstance(value, Mapping):
                continue
            key = value.get("assertion_id") or value.get("node_id") or value.get(
                "source_material_id"
            )
            if key:
                by_key[str(key)] = value

    result = []
    for assertion in assertions:
        keys = (
            assertion.assertion_id,
            assertion.node_id,
            str(assertion.metadata.get("source_material_id", "")),
        )
        verification = next((by_key[key] for key in keys if key and key in by_key), None)
        if verification is None:
            result.append(assertion)
            continue
        authority = verification.get("authority", verification)
        result.append(
            replace(
                assertion,
                metadata={**assertion.metadata, "authority": dict(authority)},
            )
        )
    return result
