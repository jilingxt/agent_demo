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
class CaseGraph:
    facts: list[Fact] = field(default_factory=list)


EvidenceGraph = CaseGraph


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
