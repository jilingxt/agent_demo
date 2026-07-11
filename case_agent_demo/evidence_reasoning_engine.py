"""Unified evidence assessment pipeline with optional case-specific Bayesian inference."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Sequence

from case_agent_demo.bayesian_engine import BayesianInferenceEngine
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


_MODEL_DIR = Path(__file__).resolve().parents[1] / "config" / "bayesian_models"
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
_BAYESIAN_NODE_BY_PREDICATE = {
    "presence": "actor_present",
    "actor_present": "actor_present",
    "physical_contact": "physical_contact",
    "violence": "violent_action",
    "violent_action": "violent_action",
    "injury_exists": "injury_exists",
    "injury_grade": "injury_grade",
    "injury_consequence": "injury_grade",
    "mechanism_compatible": "mechanism_consistency",
    "mechanism_consistency": "mechanism_consistency",
    "temporal_proximity": "temporal_consistency",
    "temporal_consistency": "temporal_consistency",
    "alternative_cause": "alternative_cause",
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
    """Run generic evidence fusion and an explicitly routed Bayesian template."""

    def __init__(
        self,
        normalizer: AssertionNormalizer | None = None,
        claim_builder: ClaimBuilderV2 | None = None,
        subjective_engine: SubjectiveEvidenceEngine | None = None,
        model_dir: str | Path | None = None,
    ):
        self.normalizer = normalizer or AssertionNormalizer()
        self.claim_builder = claim_builder or ClaimBuilderV2(self.normalizer)
        self.subjective_engine = subjective_engine or SubjectiveEvidenceEngine()
        self.model_dir = Path(model_dir) if model_dir is not None else _MODEL_DIR

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
            claim_assertions = [
                assertion for assertion in assertions if assertion.assertion_id in set(claim.assertion_ids)
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

        bayesian_result = self._infer_bayesian(case_type, scored_claims, assessments)
        model_versions = {"subjective": _SUBJECTIVE_MODEL_VERSION}
        if bayesian_result is not None:
            model_versions["bayesian"] = (
                f"{bayesian_result['model_id']}:{bayesian_result['version']}"
            )
            scored_claims, assessments = _append_causation_assessment(
                scored_claims,
                assessments,
                bayesian_result,
            )

        return EvidenceReasoningResult(
            assertions=assertions,
            claims=scored_claims,
            claim_assessments=assessments,
            bayesian_result=bayesian_result,
            reasoning_trace={
                "assertion_count": len(assertions),
                "claim_count": len(scored_claims),
                "bayesian_template": model_versions.get("bayesian", ""),
            },
            model_versions=model_versions,
        )

    def _infer_bayesian(
        self,
        case_type: str,
        claims: list[EvidenceClaim],
        assessments: list[ClaimAssessment],
    ) -> dict | None:
        model_path = self._model_path_for(case_type)
        if model_path is None:
            return None

        assessment_by_claim = {item.claim_id: item for item in assessments}
        soft_evidence: dict[str, float] = {}
        soft_evidence_sources: dict[str, list[str]] = {}
        for claim in claims:
            node_id = _BAYESIAN_NODE_BY_PREDICATE.get(claim.behavior_type)
            assessment = assessment_by_claim.get(claim.claim_id)
            if node_id is None or assessment is None or assessment.opinion is None:
                continue
            projected_support = assessment.opinion.support + 0.5 * assessment.opinion.uncertainty
            current = soft_evidence.get(node_id)
            if current is None or projected_support > current:
                soft_evidence[node_id] = projected_support
                soft_evidence_sources[node_id] = [claim.claim_id]
            elif projected_support == current:
                soft_evidence_sources.setdefault(node_id, []).append(claim.claim_id)

        result = BayesianInferenceEngine(model_path).infer(soft_evidence)
        result["soft_evidence"] = soft_evidence
        result["soft_evidence_sources"] = soft_evidence_sources
        return result

    def _model_path_for(self, case_type: str) -> Path | None:
        normalized = case_type.strip().lower().replace("-", "_")
        if "故意伤害" in case_type or "intentional injury" in normalized or "intentional_injury" in normalized:
            return self.model_dir / "intentional_injury_v1.json"
        return None


def _append_causation_assessment(
    claims: list[EvidenceClaim],
    assessments: list[ClaimAssessment],
    bayesian_result: dict,
) -> tuple[list[EvidenceClaim], list[ClaimAssessment]]:
    posterior = bayesian_result.get("node_values", {}).get("causation")
    if posterior is None:
        return claims, assessments

    action_claim = next(
        (claim for claim in claims if claim.behavior_type in {"violence", "violent_action"}),
        None,
    )
    injury_claim = next(
        (
            claim
            for claim in claims
            if claim.behavior_type in {"injury_exists", "injury_grade", "injury_consequence"}
        ),
        None,
    )
    actor = action_claim.subject if action_claim is not None else ""
    target = (
        (action_claim.target_person or action_claim.object)
        if action_claim is not None
        else ""
    ) or (
        (injury_claim.target_person or injury_claim.subject or injury_claim.object)
        if injury_claim is not None
        else ""
    )
    event_id = (
        action_claim.event_id if action_claim is not None else ""
    ) or (
        injury_claim.event_id if injury_claim is not None else ""
    )
    claim_id = f"CL-causation-{actor or 'unknown'}-{target or 'unknown'}-{event_id or 'case'}"
    model_version = f"{bayesian_result['model_id']}:{bayesian_result['version']}"
    derived_claim = EvidenceClaim(
        claim_id=claim_id,
        subject=actor,
        behavior_type="causation",
        target_person=target,
        event_id=event_id,
        confidence_profile=ConfidenceProfile(
            final_score=round(float(posterior), 4),
            label="贝叶斯派生结果（专家先验，未经历史数据校准）",
            reasons=["由跨 Claim 因果模板计算，不反向证明行为人身份或暴力行为。"],
        ),
        metadata={"derived_by": model_version},
    )
    derived_assessment = ClaimAssessment(
        claim_id=claim_id,
        status="bayesian_derived",
        support_index=round(float(posterior), 4),
        bayesian_posterior=round(float(posterior), 4),
        bayesian_model_version=model_version,
        reasons=[
            "因果结果由版本化贝叶斯模板派生。",
            "参数为未经历史数据校准的专家先验，不作为事实概率或最终法律结论。",
        ],
    )
    return [*claims, derived_claim], [*assessments, derived_assessment]

def _apply_authority_verifications(
    assertions: list[EvidenceAssertion],
    verifications: Sequence[Mapping] | Mapping[str, Mapping] | None,
) -> list[EvidenceAssertion]:
    if not verifications:
        return assertions

    if isinstance(verifications, Mapping):
        by_key = {str(key): value for key, value in verifications.items() if isinstance(value, Mapping)}
    else:
        by_key = {}
        for value in verifications:
            if not isinstance(value, Mapping):
                continue
            key = value.get("assertion_id") or value.get("node_id") or value.get("source_material_id")
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