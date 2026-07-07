from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


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
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CaseGraph:
    facts: list[Fact] = field(default_factory=list)
    nodes: list[EvidenceNode] = field(default_factory=list)
    edges: list[EvidenceEdge] = field(default_factory=list)

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
    return EvidenceNode(
        node_id=fact.fact_id,
        node_type="fact",
        source_material_id=fact.source_material_id,
        source_type=fact.source_type,
        summary=fact.behavior,
        person=fact.person,
        behavior=fact.behavior,
        time=fact.time,
        location=fact.location,
        object=fact.object,
        confidence=fact.confidence,
        human_confirmed=fact.human_confirmed,
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
    )


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
