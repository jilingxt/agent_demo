from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

NODE_TYPE_FACT = "fact"
NODE_TYPE_MATERIAL = "material"
NODE_TYPE_REPORT_OPINION = "report_opinion"

EDGE_TYPE_SOURCE_OF = "source_of"
EDGE_TYPE_SAME_PERSON = "same_person"
EDGE_TYPE_SAME_OBJECT = "same_object"
EDGE_TYPE_SAME_EVENT = "same_event"
EDGE_TYPE_SUPPORTS = "supports"
EDGE_TYPE_CONTRADICTS = "contradicts"
EDGE_TYPE_NEEDS_HUMAN_CHECK = "needs_human_check"

UNRESOLVED_PREDICATE = "unresolved_observation"


class MaterialType(StrEnum):
    STATEMENT = "statement"
    EVIDENCE_IMAGE = "evidence_image"
    REPORT_IMAGE = "report_image"


@dataclass(frozen=True)
class Material:
    material_id: str
    material_type: MaterialType
    content: str
    source_path: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CaseTypeSuggestion:
    suggested_case_types: list[dict]
    requires_human_confirmation: bool = True


@dataclass(frozen=True)
class Fact:
    fact_id: str
    source_material_id: str
    source_type: str
    person: str
    behavior: str
    time: str = ""
    location: str = ""
    object: str = ""
    confidence: float = 0.8
    human_confirmed: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceNode:
    node_id: str
    node_type: str
    source_material_id: str
    source_type: str
    summary: str
    person: str = ""
    behavior: str = ""
    time: str = ""
    location: str = ""
    object: str = ""
    confidence: float = 0.8
    polarity: str = "ambiguous"
    claim_type: str = UNRESOLVED_PREDICATE
    source_party: str = "unknown"
    observation_type: str = ""
    status: str = "active"
    version: int = 1
    raw_ref: str = ""
    human_confirmed: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    reason: str
    confidence: float = 0.8
    evidence_basis: list[str] = field(default_factory=list)
    status: str = "active"
    version: int = 1
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceProfile:
    extraction_quality: float = 0.0
    source_reliability: float = 0.0
    corroboration_score: float = 0.0
    contradiction_score: float = 0.0
    independence_score: float = 0.0
    uncertainty: float = 0.0
    final_score: float = 0.0
    label: str = ""
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    subject: str
    behavior_type: str
    object: str = ""
    time_bucket: str = ""
    location: str = ""
    supporting_node_ids: list[str] = field(default_factory=list)
    opposing_node_ids: list[str] = field(default_factory=list)
    related_edge_ids: list[str] = field(default_factory=list)
    confidence_profile: ConfidenceProfile | None = None
    status: str = "active"
    metadata: dict = field(default_factory=dict)
    target_person: str = ""
    event_id: str = ""
    assertion_ids: list[str] = field(default_factory=list)
    ambiguous_node_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceAssertion:
    assertion_id: str
    node_id: str
    declarant: str = ""
    actor: str = ""
    predicate: str = "general"
    target_person: str = ""
    object: str = ""
    event_id: str = ""
    stance: str = "ambiguous"
    modality: str = ""
    source_group: str = ""
    origin_evidence: str = ""
    metadata: dict = field(default_factory=dict)
    assertion_role: str = "context"
    time: str = ""
    location: str = ""
    evidence_category: str = ""
    declarant_role: str = ""


@dataclass(frozen=True)
class ClaimOpinion:
    claim_id: str
    support: float = 0.0
    opposition: float = 0.0
    uncertainty: float = 1.0
    conflict: float = 0.0


@dataclass(frozen=True)
class AuthorityAssessment:
    issuer: str = ""
    document_type: str = ""
    competence_verified: bool = False
    authenticity_verified: bool = False
    procedure_verified: bool = False
    subject_identity_verified: bool = False
    method_verified: bool = False
    standard_verified: bool = False
    scope_verified: bool = False
    defeater: bool = False
    status: str = "unverified"
    mean: float = 0.0
    strength: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClaimAssessment:
    claim_id: str
    opinion: ClaimOpinion | None = None
    status: str = "unassessed"
    reasons: list[str] = field(default_factory=list)
    authority_assessments: list[AuthorityAssessment] = field(default_factory=list)
    support_index: float = 0.0
    bayesian_posterior: float | None = None
    bayesian_model_version: str = ""


@dataclass(frozen=True)
class CaseTypeContext:
    value: str = ""
    status: str = "unknown"
    source: str = "automatic"
    candidates: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParticipantRecord:
    name: str
    roles: list[str] = field(default_factory=list)
    assertion_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AllegationRecord:
    allegation_id: str
    reporter: str
    alleged_actor: str
    predicate: str
    factual_summary: str
    target_person: str = ""
    object: str = ""
    time: str = ""
    location: str = ""
    assertion_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceFinding:
    claim_id: str
    subject: str
    predicate: str
    status: str
    target_person: str = ""
    object: str = ""
    time: str = ""
    location: str = ""
    supporting_node_ids: list[str] = field(default_factory=list)
    opposing_node_ids: list[str] = field(default_factory=list)
    ambiguous_node_ids: list[str] = field(default_factory=list)
    support_index: float = 0.0
    reasons: list[str] = field(default_factory=list)
    conclusion: str = ""


@dataclass(frozen=True)
class ObjectiveCircumstance:
    node_id: str
    source_material_id: str
    category: str
    summary: str
    time: str = ""
    location: str = ""


@dataclass(frozen=True)
class IdentificationRecord:
    node_id: str
    source_material_id: str
    identifier: str
    identified_person: str
    summary: str
    time: str = ""
    location: str = ""


@dataclass(frozen=True)
class LegalCandidate:
    law_id: str
    law_name: str
    article: str
    retrieval_purpose: str
    candidate_basis: str = ""
    matched_elements: list[str] = field(default_factory=list)
    missing_elements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvidenceBook:
    participants: list[ParticipantRecord] = field(default_factory=list)
    allegations: list[AllegationRecord] = field(default_factory=list)
    fact_findings: list[EvidenceFinding] = field(default_factory=list)
    objective_circumstances: list[ObjectiveCircumstance] = field(default_factory=list)
    identifications: list[IdentificationRecord] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    legal_candidates: list[LegalCandidate] = field(default_factory=list)
    bayesian_runs: list[dict] = field(default_factory=list)
    bayesian_abstentions: list[dict] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    conclusion_boundary: str = ""


@dataclass(frozen=True)
class LegalDomain:
    domain_id: str
    name: str
    parent_id: str = ""
    aliases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class DomainAffinity:
    domain_id: str
    score: float
    source: str = "auto"
    reason: str = ""


@dataclass(frozen=True)
class LegalDocument:
    document_id: str
    title: str
    doc_type: str
    source_path: str
    source: str = ""
    version: str = "v1"
    document_hash: str = ""
    effective_status: str = "effective"
    domain_affinities: list[DomainAffinity] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LegalChunk:
    chunk_id: str
    document_id: str
    text: str
    title: str = ""
    article: str = ""
    clause: str = ""
    doc_type: str = ""
    keywords: list[str] = field(default_factory=list)
    legal_elements: list[str] = field(default_factory=list)
    domain_affinities: list[DomainAffinity] = field(default_factory=list)
    score: float = 0.0
    effective_status: str = "effective"
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LegalRAGResult:
    matches: list["LegalMatch"]
    chunks: list[LegalChunk]
    query: str
    purpose: str
    cache_hit: bool = False
    query_trace: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CaseGraph:
    facts: list[Fact] = field(default_factory=list)
    nodes: list[EvidenceNode] = field(default_factory=list)
    edges: list[EvidenceEdge] = field(default_factory=list)
    claims: list[EvidenceClaim] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.nodes and self.facts:
            object.__setattr__(self, "nodes", [fact_to_node(fact) for fact in self.facts])
        if not self.facts and self.nodes:
            object.__setattr__(
                self,
                "facts",
                [node_to_fact(node) for node in self.nodes if node.node_type == "fact"],
            )


EvidenceGraph = CaseGraph


def fact_to_node(fact: Fact) -> EvidenceNode:
    metadata = dict(fact.metadata)
    assertions = metadata.get("assertions")
    first_assertion = (
        assertions[0]
        if isinstance(assertions, list) and assertions and isinstance(assertions[0], dict)
        else {}
    )
    return EvidenceNode(
        node_id=fact.fact_id,
        node_type=NODE_TYPE_FACT,
        source_material_id=fact.source_material_id,
        source_type=fact.source_type,
        summary=fact.behavior,
        person=fact.person,
        behavior=fact.behavior,
        time=fact.time,
        location=fact.location,
        object=fact.object,
        confidence=fact.confidence,
        polarity=str(metadata.get("stance") or first_assertion.get("stance") or "ambiguous"),
        claim_type=str(
            metadata.get("predicate")
            or first_assertion.get("predicate")
            or UNRESOLVED_PREDICATE
        ),
        observation_type=fact.source_type,
        human_confirmed=fact.human_confirmed,
        metadata=metadata,
    )


def node_to_fact(node: EvidenceNode) -> Fact:
    return Fact(
        fact_id=node.node_id,
        source_material_id=node.source_material_id,
        source_type=node.source_type,
        person=node.person,
        behavior=node.behavior or node.summary,
        time=node.time,
        location=node.location,
        object=node.object,
        confidence=node.confidence,
        human_confirmed=node.human_confirmed,
        metadata=dict(node.metadata),
    )


def infer_polarity(text: str) -> str:
    del text
    return "ambiguous"


def infer_claim_type(behavior: str, obj: str = "") -> str:
    predicates = infer_claim_types(behavior, obj)
    return predicates[0] if predicates else "general"


def infer_claim_types(behavior: str, obj: str = "") -> list[str]:
    del behavior, obj
    return [UNRESOLVED_PREDICATE]


def infer_predicate_stance(text: str, predicate: str) -> str:
    del text, predicate
    return "ambiguous"


@dataclass(frozen=True)
class Conflict:
    conflict_id: str
    conflict_type: str
    claim_a: str
    claim_b: str
    source_a: str
    source_b: str
    severity: str
    need_user_confirm: bool = True


@dataclass(frozen=True)
class LegalMatch:
    law_id: str
    law_name: str
    article: str
    legal_element: str
    matched_behavior: str
    source: str
    effective_status: str = "demo_preloaded"


@dataclass(frozen=True)
class Challenge:
    challenge_id: str
    challenge_type: str
    target: str
    reason: str
    severity: str = "medium"
    requires_revision: bool = True


@dataclass(frozen=True)
class ReviewResult:
    status: str
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowResult:
    confirmed_case_type: str
    executed_agents: list[str]
    case_graph: CaseGraph
    legal_matches: list[LegalMatch]
    conflicts: list[Conflict]
    challenges: list[Challenge]
    draft_report: str
    final_report: str
    report: str
    review: ReviewResult
    evidence_graph: CaseGraph | None = None
    material_plan: object | None = None
    validation_issues: list[object] = field(default_factory=list)
    assertions: list[EvidenceAssertion] = field(default_factory=list)
    claim_assessments: list[ClaimAssessment] = field(default_factory=list)
    bayesian_result: dict | None = None
    reasoning_trace: dict = field(default_factory=dict)
    model_versions: dict = field(default_factory=dict)
    case_type_context: CaseTypeContext = field(default_factory=CaseTypeContext)
    evidence_book: EvidenceBook | None = None
    inferred_case_domains: list[str] = field(default_factory=list)
