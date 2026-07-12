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
    polarity: str = "affirm"
    claim_type: str = ""
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
        polarity=infer_polarity(fact.behavior),
        claim_type=infer_claim_type(fact.behavior, fact.object),
        observation_type=fact.source_type,
        human_confirmed=fact.human_confirmed,
        metadata=dict(fact.metadata),
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
    if any(word in text for word in ("疑似", "可能", "不确定", "无法确认")):
        return "uncertain"
    denial_phrases = (
        "没有", "否认", "不承认", "没打", "没拿", "没去",
        "未实施", "未到场", "未拿取", "未发现", "尚未",
    )
    if any(phrase in text for phrase in denial_phrases):
        return "deny"
    return "affirm"


def infer_claim_type(behavior: str, obj: str = "") -> str:
    predicates = infer_claim_types(behavior, obj)
    return predicates[0] if predicates else "general"


def infer_claim_types(behavior: str, obj: str = "") -> list[str]:
    text = f"{behavior} {obj}"
    rules = (
        ("alternative_cause", ("其他合理原因", "其他合理致伤原因", "其他致伤原因", "另有原因", "自行摔倒")),
        ("mechanism_compatible", ("机制吻合", "作用机制吻合", "形成机制一致")),
        ("temporal_proximity", ("时间接近", "立即出现", "紧接着出现")),
        ("alternative_explanation", ("借用", "误拿", "受托保管", "替代性解释")),
        ("possession_transfer", ("转移到", "转移占有", "交付后控制", "取得控制")),
        ("prior_possession", ("原先占有", "保管并占有", "原持有人", "原由其保管")),
        ("property_trace", ("财物去向", "已被追回", "赃物", "交易记录")),
        ("persistence_or_group", ("持续起哄", "多人参与", "聚众", "反复实施")),
        ("operational_impact", ("停止营业", "通行受到影响", "交通中断", "无法办公")),
        ("public_context", ("公共场所", "车站大厅", "医院大厅", "商场内")),
        ("public_order_conduct", ("扰乱秩序", "冲闯", "起哄滋事", "妨碍场所秩序")),
        ("exposure", ("不特定多数人", "暴露范围", "公共区域受威胁")),
        ("control_failure", ("未采取控制措施", "失去控制", "泄漏且未", "控制失效")),
        ("hazardous_conduct", ("纵火", "引爆", "投放危险物质", "危险驾驶")),
        ("dangerous_object_or_condition", ("爆炸物", "危险物质", "易燃易爆", "危险状态")),
        ("duty_record_present", ("义务文书", "职责记录", "管理义务记录", "岗位职责")),
        ("qualification_record_present", ("资格证书", "任职证明", "从业资格记录", "资格文书")),
        ("authorization_record_absent", ("未发现许可证", "无授权记录", "许可证缺失", "授权文件缺失")),
        ("conduct_recorded", ("行为记录", "执法记录显示", "监控记录显示", "书面记录显示")),
        ("damage_exists", ("损坏结果", "无法使用", "功能丧失", "维修损失")),
        ("violence", ("打架", "动手", "殴打", "伤害", "抱摔", "推搡", "掐脖子", "拉拽")),
        ("injury_consequence", ("轻伤", "重伤", "骨折", "伤情", "鉴定意见", "损伤")),
        ("property_damage", ("损坏", "毁坏", "砸坏", "摔坏", "破坏")),
        ("taking_property", ("拿走", "窃取", "盗窃", "非法占有", "拿取", "偷走")),
        ("presence", ("现场", "出现", "在场", "不在", "在家")),
    )
    result = [predicate for predicate, keywords in rules if any(word in text for word in keywords)]
    return list(dict.fromkeys(result)) or ["general"]


def infer_predicate_stance(text: str, predicate: str) -> str:
    if predicate == "alternative_cause" and any(
        phrase in text for phrase in ("排除", "不存在其他", "无其他合理", "未发现其他")
    ):
        return "deny"
    return infer_polarity(text)


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
