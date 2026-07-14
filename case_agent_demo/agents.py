from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from langchain_core.runnables import RunnableLambda

from case_agent_demo.graph_store import GraphStoreTool
from case_agent_demo.models import (
    CaseGraph,
    CaseTypeSuggestion,
    Challenge,
    Conflict,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    Fact,
    LegalMatch,
    Material,
    MaterialType,
    ReviewResult,
    UNRESOLVED_PREDICATE,
    fact_to_node,
)
from case_agent_demo.config import ModelProfile, ModelProfiles
from case_agent_demo.material_plan import MaterialPlan
from case_agent_demo.relation_tools import RelationRuleTool
from case_agent_demo.tools import LegalRetrievalTool, RagLegalAgent
from case_agent_demo.vision_tools import ImageEvidenceDescription


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _shorten(text: str, limit: int = 110) -> str:
    text = _compact_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，,；;、 ") + "…"


def _should_use_vision_tool(material: Material) -> bool:
    content = material.content.strip()
    return bool(material.source_path and (not content or "Qwen" in content))


def _image_description_content(description: ImageEvidenceDescription) -> str:
    return description.to_material_content()


def _statement_user_input(material: Material) -> str:
    return (
        f"material_id: {material.material_id}\n"
        f"material_type: {material.material_type.value}\n"
        f"source_path: {material.source_path}\n\n"
        f"{material.content}"
    )


def _materials_user_input(materials: list[Material]) -> str:
    return "\n\n--- material ---\n\n".join(
        (
            f"material_id: {material.material_id}\n"
            f"material_type: {material.material_type.value}\n"
            f"source_path: {material.source_path}\n\n"
            f"{material.content}"
        )
        for material in materials
    )


def _case_type_suggestion_from_json(data: dict[str, Any]) -> CaseTypeSuggestion:
    suggestions = data.get("suggested_case_types", [])
    if not isinstance(suggestions, list):
        suggestions = []
    return CaseTypeSuggestion(
        suggested_case_types=[item for item in suggestions if isinstance(item, dict)],
        requires_human_confirmation=bool(data.get("requires_human_confirmation", True)),
    )


def _unknown_case_type_suggestion(reason: str) -> CaseTypeSuggestion:
    return CaseTypeSuggestion(
        suggested_case_types=[
            {
                "case_type": "待人工判断案件",
                "domain_id": "unknown",
                "confidence": 0.0,
                "basis": [reason],
                "requires_human_confirmation": True,
            }
        ],
        requires_human_confirmation=True,
    )


def _reasoning_user_input(payload: dict[str, Any]) -> str:
    graph: EvidenceGraph = payload["evidence_graph"]
    laws: list[LegalMatch] = payload["legal_matches"]
    conflicts: list[Conflict] = payload["conflicts"]
    fact_lines = "\n".join(
        (
            f"{fact.fact_id}|source={fact.source_material_id}|person={fact.person}|"
            f"behavior={fact.behavior}|time={fact.time}|location={fact.location}|object={fact.object}"
        )
        for fact in graph.facts
    )
    law_lines = "\n".join(f"{law.law_id}|{law.law_name}|{law.article}|{law.legal_element}" for law in laws)
    conflict_lines = "\n".join(f"{item.conflict_id}|{item.conflict_type}|{item.source_a}|{item.source_b}|{item.severity}" for item in conflicts)
    assessment_lines = _claim_assessment_text(payload)
    return (
        f"confirmed_case_type: {payload['confirmed_case_type']}\n\n"
        f"case_graph_facts:\n{fact_lines}\n\n"
        f"claim_assessments:\n{assessment_lines}\n\n"
        f"legal_matches:\n{law_lines}\n\n"
        f"conflicts:\n{conflict_lines}"
    )


def _reasoning_fallback(payload: dict[str, Any]) -> str:
    return ReasoningAgent().reason(payload)


def _claim_assessment_text(payload: dict[str, Any]) -> str:
    assessments = payload.get("claim_assessments") or []
    if not assessments:
        return "未提供 Claim 级评估。"
    return "\n".join(
        f"{item.claim_id}|status={item.status}|support_index={item.support_index}|"
        f"reasons={'；'.join(item.reasons)}"
        for item in assessments
    )


def _node_assessment_status(payload: dict[str, Any]) -> dict[str, str]:
    graph: EvidenceGraph = payload["evidence_graph"]
    status_by_claim = {
        item.claim_id: item.status
        for item in payload.get("claim_assessments") or []
    }
    result: dict[str, str] = {}
    for claim in graph.claims:
        status = status_by_claim.get(claim.claim_id, "")
        for node_id in (
            claim.supporting_node_ids
            + claim.opposing_node_ids
            + claim.ambiguous_node_ids
        ):
            result[node_id] = status
    return result


def _fact_assessment_prefix(status: str) -> str:
    return {
        "authority_anchored": "权威材料支持",
        "supported": "现有材料支持",
        "contested": "争议材料（尚不能作为确定事实）",
        "contested_but_not_refuted": "争议材料（尚不能作为确定事实）",
        "insufficient": "证据不足（待补强）",
        "opposing_dominant": "反向证据占优（不得作为确定事实）",
        "authority_contested": "权威意见存在争议",
    }.get(status, "待评估材料")


def _unresolved_fact(
    material: Material,
    *,
    content: str | None = None,
    confidence: float = 0.0,
    reason: str = "semantic_runtime_unavailable",
) -> Fact:
    raw_text = content if content is not None else material.content
    assertion = {
        "declarant": "",
        "actor": "",
        "target_person": "",
        "object": "",
        "predicate": UNRESOLVED_PREDICATE,
        "stance": "ambiguous",
        "event_id": f"MATERIAL-{material.material_id}",
        "source_group": material.material_id,
        "origin_evidence": material.material_id,
        "assertion_role": "context",
        "evidence_category": material.material_type.value,
        "evidence_span": raw_text,
    }
    return Fact(
        fact_id=f"F-{material.material_id}-UNRESOLVED",
        source_material_id=material.material_id,
        source_type=material.material_type.value,
        person="",
        behavior=_shorten(raw_text, 120),
        confidence=max(0.0, min(1.0, confidence)),
        metadata={
            **assertion,
            "assertions": [assertion],
            "semantic_status": "unresolved",
            "semantic_reason": reason,
            "raw_text": raw_text,
        },
    )


def _facts_from_json(data: dict[str, Any], material: Material) -> list[Fact]:
    raw_facts = data.get("facts", [])
    if not isinstance(raw_facts, list):
        return []
    facts: list[Fact] = []
    for index, item in enumerate(raw_facts, start=1):
        if not isinstance(item, dict):
            continue
        predicate = str(item.get("predicate") or "").strip()
        stance = str(item.get("stance") or "").strip()
        if not predicate or stance not in {"affirm", "deny", "ambiguous"}:
            continue
        metadata = dict(item.get("metadata", {})) if isinstance(item.get("metadata"), dict) else {}
        for key in (
            "actor", "target_person", "predicate", "event_id", "stance", "source_group",
            "origin_evidence", "declarant", "assertion_role",
            "declarant_role", "evidence_category", "modality", "evidence_span",
            "object", "time", "location", "legal_query_terms", "element_role",
        ):
            if key in item:
                metadata[key] = item[key]
        assertions = [
            {
                key: metadata.get(key, "")
                for key in (
                    "declarant", "actor", "target_person", "object", "predicate",
                    "stance", "event_id", "source_group", "origin_evidence",
                    "assertion_role", "declarant_role", "evidence_category",
                    "modality", "evidence_span", "legal_query_terms", "element_role",
                )
            }
        ]
        metadata["assertions"] = assertions
        metadata["semantic_status"] = "resolved"
        facts.append(
            Fact(
                fact_id=str(item.get("fact_id") or f"F-{material.material_id}-TEXT-{index}"),
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=str(item.get("person", "")),
                behavior=_shorten(str(item.get("behavior", "")), 120),
                time=str(item.get("time", "")),
                location=str(item.get("location", "")),
                object=str(item.get("object", "")),
                confidence=float(item.get("confidence", 0.8) or 0.8),
                metadata=metadata,
            )
        )
    return facts or [
        _unresolved_fact(material, reason="invalid_semantic_output")
    ]

@dataclass
class PlanningAgent:
    name: str = "planning_agent"
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().planning

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self._suggest)

    def suggest(self, materials: list[Material]) -> CaseTypeSuggestion:
        return self.runnable.invoke(materials)

    def plan_materials(self, materials: list[Material]) -> MaterialPlan:
        return MaterialPlan.from_materials(materials)

    def _suggest(self, materials: list[Material]) -> CaseTypeSuggestion:
        if self.runtime is not None:
            return self.runtime.run_json(
                "planning_agent",
                self.profile,
                _materials_user_input(materials),
                fallback=lambda: _unknown_case_type_suggestion("语义模型不可用或输出无效"),
                parser=_case_type_suggestion_from_json,
            )
        return _unknown_case_type_suggestion("未配置语义模型，不根据原文关键词猜测案件类型")


@dataclass
class TextAgent:
    name: str = "text_agent"
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().text

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        if self.runtime is not None:
            return self.runtime.run_json(
                "text_agent",
                self.profile,
                _statement_user_input(material),
                fallback=lambda: self._extract_fallback(material),
                parser=lambda data: _facts_from_json(data, material),
            )
        return self._extract_fallback(material)

    def _extract_fallback(self, material: Material) -> list[Fact]:
        return [_unresolved_fact(material)]


@dataclass
class PicAgent:
    name: str = "pic_agent"
    vision_tool: Any | None = None
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().text

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        content = material.content
        confidence = 0.9
        if self.vision_tool is not None and _should_use_vision_tool(material):
            description = self.vision_tool.describe(material)
            content = _image_description_content(description)
            confidence = description.confidence
        return self._fact_from_content(material, content, confidence)

    def extract_group(self, group_id: str, image_paths: list[str]) -> list[Fact]:
        if self.vision_tool is None:
            content = f"Image group pending Qwen vision: {group_id}"
            confidence = 0.0
        else:
            description = self.vision_tool.describe_group(group_id, image_paths)
            content = _image_description_content(description)
            confidence = description.confidence
        material = Material(group_id, MaterialType.EVIDENCE_IMAGE, content, source_path=";".join(image_paths))
        return self._fact_from_content(material, content, confidence)

    def _fact_from_content(self, material: Material, content: str, confidence: float) -> list[Fact]:
        if self.runtime is None:
            return [
                _unresolved_fact(
                    material,
                    content=content,
                    confidence=confidence,
                    reason="image_semantic_runtime_unavailable",
                )
            ]
        return self.runtime.run_json(
            "image_evidence_agent",
            self.profile,
            _materials_user_input([replace(material, content=content)]),
            fallback=lambda: [
                _unresolved_fact(
                    material,
                    content=content,
                    confidence=confidence,
                    reason="invalid_image_semantic_output",
                )
            ],
            parser=lambda data: _facts_from_json(data, replace(material, content=content)),
        )

@dataclass
class ReportImageAgent:
    name: str = "report_image_agent"
    legal_tool: LegalRetrievalTool | None = None
    vision_tool: Any | None = None
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().reasoning

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        content = material.content
        confidence = 0.0
        if self.vision_tool is not None and _should_use_vision_tool(material):
            description = self.vision_tool.describe(material)
            content = _image_description_content(description)
            confidence = description.confidence
        return self._fact_from_content(material, content, confidence)

    def extract_group(self, group_id: str, image_paths: list[str]) -> list[Fact]:
        if self.vision_tool is None:
            content = f"Report image group pending Qwen vision: {group_id}"
            confidence = 0.0
        else:
            description = self.vision_tool.describe_group(group_id, image_paths)
            content = _image_description_content(description)
            confidence = description.confidence
        material = Material(group_id, MaterialType.REPORT_IMAGE, content, source_path=";".join(image_paths))
        return self._fact_from_content(material, content, confidence)

    def _fact_from_content(self, material: Material, content: str, confidence: float) -> list[Fact]:
        if self.runtime is None:
            return [
                _unresolved_fact(
                    material,
                    content=content,
                    confidence=confidence,
                    reason="report_semantic_runtime_unavailable",
                )
            ]
        semantic_material = replace(material, content=content)
        return self.runtime.run_json(
            "report_image_agent",
            self.profile,
            _materials_user_input([semantic_material]),
            fallback=lambda: [
                _unresolved_fact(
                    material,
                    content=content,
                    confidence=confidence,
                    reason="invalid_report_semantic_output",
                )
            ],
            parser=lambda data: _facts_from_json(data, semantic_material),
        )


@dataclass
class EvidenceGraphAgent:
    name: str = "case_graph_agent"
    legal_tool: LegalRetrievalTool | None = None
    relation_tool: RelationRuleTool = field(default_factory=RelationRuleTool)

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.build)

    def add_fact(self, store: GraphStoreTool, fact: Fact) -> EvidenceNode:
        material_node = _material_node_for_fact(fact)
        fact_node = fact_to_node(fact)
        existing_nodes = [node for node in store.list_nodes() if node.node_type == "fact"]

        store.add_node(material_node)
        store.add_node(fact_node)
        store.add_edge(
            EvidenceEdge(
                edge_id=f"E-{material_node.node_id}-{fact_node.node_id}-source_of",
                source_node_id=material_node.node_id,
                target_node_id=fact_node.node_id,
                edge_type="source_of",
                reason="材料生成事实节点。",
                confidence=fact.confidence,
                evidence_basis=[fact.source_material_id, fact.fact_id],
            )
        )
        for edge in self.relation_tool.infer_edges_for_new_node(fact_node, existing_nodes):
            store.add_edge(edge)
        return fact_node

    def build(self, facts: list[Fact]) -> CaseGraph:
        store = GraphStoreTool()
        for fact in facts:
            self.add_fact(store, fact)
        return store.to_graph()


CaseGraphAgent = EvidenceGraphAgent


def _material_node_for_fact(fact: Fact) -> EvidenceNode:
    return EvidenceNode(
        node_id=f"M-{fact.source_material_id}",
        node_type="material",
        source_material_id=fact.source_material_id,
        source_type=fact.source_type,
        summary=f"材料 {fact.source_material_id}",
        confidence=1.0,
    )


@dataclass(frozen=True)
class _ConflictClaim:
    fact: Fact
    polarity: str
    claim_types: tuple[str, ...]
    target_keys: tuple[str, ...]


def _classify_conflict_claims(fact: Fact) -> list[_ConflictClaim]:
    assertions = fact.metadata.get("assertions")
    if isinstance(assertions, list):
        structured = [
            _conflict_claim_from_assertion(fact, assertion)
            for assertion in assertions
            if isinstance(assertion, dict) and assertion.get("predicate")
        ]
        if structured:
            return structured
    return []


def _conflict_claim_from_assertion(fact: Fact, assertion: dict[str, Any]) -> _ConflictClaim:
    predicate = str(assertion.get("predicate") or "general")
    stance = str(assertion.get("stance") or "ambiguous")
    return _ConflictClaim(
        fact=fact,
        polarity="affirm" if stance == "affirm" else "deny" if stance == "deny" else "ambiguous",
        claim_types=(predicate,),
        target_keys=_claim_target_keys(fact, assertion),
    )


def _claim_target_keys(fact: Fact, assertion: dict[str, Any] | None = None) -> tuple[str, ...]:
    assertion = assertion or {}
    direct_targets = (
        assertion.get("object"),
        assertion.get("target_person"),
        fact.object,
    )
    candidates = direct_targets if any(direct_targets) else (
        assertion.get("actor"),
        fact.person,
    )
    keys: list[str] = []
    for candidate in candidates:
        cleaned = re.sub(r"\s+", "", str(candidate or ""))
        if cleaned and cleaned not in keys:
            keys.append(cleaned)
    return tuple(keys)


def _objects_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return False
    return any(
        left_key in right_key or right_key in left_key
        for left_key in left
        for right_key in right
    )


def _claim_conflict_type(left: _ConflictClaim, right: _ConflictClaim) -> str:
    if {left.polarity, right.polarity} != {"affirm", "deny"}:
        return ""
    if not _objects_overlap(left.target_keys, right.target_keys):
        return ""
    left_types = set(left.claim_types)
    right_types = set(right.claim_types)
    if left_types & right_types:
        return "presence_conflict" if "presence" in left_types | right_types else "direct_fact_contradiction"
    if (
        ("violence" in left_types and "injury_consequence" in right_types)
        or ("injury_consequence" in left_types and "violence" in right_types)
    ):
        return "denial_vs_consequence"
    return ""


@dataclass
class ConflictAgent:
    name: str = "conflict_agent"

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.detect)

    def detect(self, graph: EvidenceGraph) -> list[Conflict]:
        conflicts: list[Conflict] = []
        claims = [
            claim
            for fact in graph.facts
            for claim in _classify_conflict_claims(fact)
        ]
        counter = 1
        seen: set[tuple[str, str, str]] = set()
        for left in claims:
            for right in claims:
                if left.fact.fact_id == right.fact.fact_id:
                    continue
                conflict_type = _claim_conflict_type(left, right)
                if not conflict_type:
                    continue
                key = tuple(sorted((left.fact.fact_id, right.fact.fact_id))) + (conflict_type,)
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(
                    Conflict(
                        conflict_id=f"C-{counter}",
                        conflict_type=conflict_type,
                        claim_a=left.fact.behavior,
                        claim_b=right.fact.behavior,
                        source_a=left.fact.source_material_id,
                        source_b=right.fact.source_material_id,
                        severity="high",
                    )
                )
                counter += 1
        return conflicts


@dataclass
class ReasoningAgent:
    name: str = "reasoning_agent"
    runtime: Any | None = None
    profile: ModelProfile = ModelProfiles().reasoning
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.reason)

    def retrieve_legal_matches(self, payload: dict[str, Any]) -> list[LegalMatch]:
        if self.legal_tool is None:
            return list(payload.get("legal_matches", []))
        return self.legal_tool.retrieve({**payload, "purpose": "reasoning_legal_basis"})

    def reason(self, payload: dict[str, Any]) -> str:
        if self.runtime is not None:
            return self.runtime.run_json(
                "reasoning_agent",
                self.profile,
                _reasoning_user_input(payload),
                fallback=lambda: _reasoning_fallback(payload),
                parser=lambda data: str(data.get("report", "")) or _reasoning_fallback(payload),
            )
        graph: EvidenceGraph = payload["evidence_graph"]
        laws: list[LegalMatch] = payload["legal_matches"]
        conflicts: list[Conflict] = payload["conflicts"]
        case_type = payload["confirmed_case_type"]
        status_by_node = _node_assessment_status(payload)
        fact_lines = "\n".join(
            f"- {_fact_assessment_prefix(status_by_node.get(fact.fact_id, ''))}："
            f"{fact.person or '未识别人员'}：{fact.behavior}（来源 {fact.source_material_id}）"
            for fact in graph.facts
        )
        time_location_lines = "\n".join(
            f"- {fact.source_material_id}：{fact.time or '时间待核实'}；{fact.location or '地点待核实'}"
            for fact in graph.facts
        )
        object_lines = "\n".join(
            f"- {fact.source_material_id}：{fact.object}"
            for fact in graph.facts
            if fact.object
        )
        if not object_lines:
            object_lines = "- 暂未提取到明确对象或后果。"
        law_lines = "\n".join(f"- {law.law_name}{law.article}：{law.legal_element}" for law in laws)
        if not law_lines:
            law_lines = "- 暂未匹配到静态法律依据。"
        conflict_lines = "\n".join(f"- {item.conflict_type}：{item.source_a} 与 {item.source_b} 需人工核对" for item in conflicts)
        if not conflict_lines:
            conflict_lines = "- 暂未发现结构化规则可识别的冲突。"
        case_type_context = payload.get("case_type_context")
        if case_type and getattr(case_type_context, "status", "confirmed") == "confirmed":
            case_heading = f"人工确认案件类型：{case_type}"
        else:
            domains = "、".join(getattr(case_type_context, "domains", []) or [])
            case_heading = f"自动识别事实领域：{domains or '尚未形成稳定分类'}"
        return (
            f"{case_heading}\n\n"
            f"现有证据显示（行为事实）：\n{fact_lines}\n\n"
            f"时间地点：\n{time_location_lines}\n\n"
            f"对象与后果：\n{object_lines}\n\n"
            f"可能关联的法律依据：\n{law_lines}\n\n"
            f"冲突与纰漏提示：\n{conflict_lines}\n\n"
            "结论边界：以上内容仅为基于现有材料的辅助分析，仍需人工复核和补强。"
        )

    def revise(self, draft_report: str, challenges: list[Challenge]) -> str:
        if not challenges:
            return draft_report + "\n\n反方质询：未发现需要修订的关键挑战。"
        challenge_lines = "\n".join(
            f"- {item.challenge_type}：{item.reason}（对象：{item.target}，需人工确认）"
            for item in challenges
        )
        return (
            f"{draft_report}\n\n"
            f"反方质询与修订：\n{challenge_lines}\n\n"
            "修订说明：以上争议点不作确定性结论，标记为需人工确认或需补强证据。"
        )


@dataclass
class JudgeAgent:
    name: str = "judge_agent"
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.challenge)

    def challenge(self, payload: dict[str, Any]) -> list[Challenge]:
        draft_report: str = payload["draft_report"]
        conflicts: list[Conflict] = payload["conflicts"]
        legal_matches: list[LegalMatch] = payload.get("legal_matches", [])
        if not legal_matches and self.legal_tool is not None:
            legal_matches = self.legal_tool.retrieve({**payload, "purpose": "judge_legal_challenge"})
        challenges: list[Challenge] = []
        for idx, conflict in enumerate(conflicts, start=1):
            if conflict.severity == "high":
                challenges.append(
                    Challenge(
                        challenge_id=f"J-{idx}",
                        challenge_type="unresolved_conflict",
                        target=conflict.conflict_id,
                        reason=f"高严重度冲突 {conflict.source_a}/{conflict.source_b} 需要 Reasoning 明确收窄结论。",
                        severity="high",
                    )
                )
        if any(phrase in draft_report for phrase in ("已经构成犯罪", "应当处罚", "必然构成")):
            challenges.append(
                Challenge(
                    challenge_id=f"J-{len(challenges) + 1}",
                    challenge_type="overstated_legal_conclusion",
                    target="draft_report",
                    reason="Reasoning 初稿包含最终性法律判断，必须改为辅助分析表述。",
                    severity="high",
                )
            )
        if not legal_matches:
            challenges.append(
                Challenge(
                    challenge_id=f"J-{len(challenges) + 1}",
                    challenge_type="missing_legal_basis",
                    target="legal_matches",
                    reason="缺少可追溯法条来源，不能进行法律要件匹配。",
                    severity="high",
                )
            )
        return challenges


@dataclass
class ReviewAgent:
    name: str = "review_agent"
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(lambda payload: self.review(**payload))

    def review(
        self,
        report: str,
        supporting_fact_ids: list[str],
        supporting_law_ids: list[str],
        challenges: list[Challenge] | None = None,
    ) -> ReviewResult:
        issues: list[str] = []
        forbidden_phrases = ("已经构成犯罪", "应当处罚", "必然构成", "依法应当追究")
        if any(phrase in report for phrase in forbidden_phrases):
            issues.append("包含最终性法律判断，demo 只能输出辅助分析。")
        if not supporting_fact_ids:
            issues.append("缺少证据事实来源。")
        if not supporting_law_ids:
            issues.append("缺少 RAG 法条来源。")
        high_challenges = [item for item in challenges or [] if item.severity == "high"]
        if high_challenges and "反方质询" not in report:
            issues.append("未回应 Judge Agent 提出的高严重度挑战。")
        return ReviewResult(status="FAIL" if issues else "PASS", issues=issues)
