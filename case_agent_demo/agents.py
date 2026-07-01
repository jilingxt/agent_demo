from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableLambda

from case_agent_demo.models import (
    CaseGraph,
    CaseTypeSuggestion,
    Challenge,
    Conflict,
    EvidenceGraph,
    Fact,
    LegalMatch,
    Material,
    MaterialType,
    ReviewResult,
)
from case_agent_demo.config import ModelProfile, ModelProfiles
from case_agent_demo.material_plan import MaterialPlan
from case_agent_demo.tools import LegalRetrievalTool, RagLegalAgent
from case_agent_demo.vision_tools import ImageEvidenceDescription


def _find_person(text: str) -> str:
    normalized = re.sub(r"\s+", "", text)
    label_patterns = [
        r"嫌疑人([\u4e00-\u9fa5]{2,4}?)(?=首先|先|将|把|与|和|，|,|。|$)",
        r"被询问人([\u4e00-\u9fa5]{2,4}?)(?=问[:：]|男|女|，|,|。|$)",
        r"被鉴定人[:：]?([\u4e00-\u9fa5]{2,4}?)(?=，|,|。|男|女|所受|$)",
        r"受害人([\u4e00-\u9fa5]{2,4}?)(?=被|被鉴定|，|,|。|$)",
        r"答[:：]?我叫([\u4e00-\u9fa5]{2,4}?)(?=，|,|。|男|女|$)",
    ]
    for pattern in label_patterns:
        match = re.search(pattern, normalized)
        if match:
            person = _clean_person_candidate(match.group(1))
            if person:
                return person

    match = re.search(r"([\u4e00-\u9fa5]{2,3})(?:称|出现在|没有|参与)", normalized)
    if not match:
        return "未识别人员"
    person = _clean_person_candidate(match.group(1))
    if not person:
        return "未识别人员"
    if len(person) == 3 and person[0] in "年月日时分秒点第":
        return person[1:]
    return person


def _clean_person_candidate(candidate: str) -> str:
    person = candidate.strip("：:，,。；;、 ")
    bad_fragments = ("我", "你", "他", "她", "其", "本所", "我所", "首先", "之后", "工作", "司法", "鉴定")
    if any(fragment in person for fragment in bad_fragments):
        return ""
    return person

def _find_time(text: str) -> str:
    match = re.search(r"(\d{1,2}?(?:\d{1,2}?)?)", text)
    return match.group(1) if match else ""


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


def _planning_fallback(materials: list[Material]) -> CaseTypeSuggestion:
    return PlanningAgent()._suggest(materials)


def _reasoning_user_input(payload: dict[str, Any]) -> str:
    graph: EvidenceGraph = payload["evidence_graph"]
    laws: list[LegalMatch] = payload["legal_matches"]
    conflicts: list[Conflict] = payload["conflicts"]
    fact_lines = "\n".join(f"{fact.fact_id}|{fact.source_material_id}|{fact.person}|{fact.behavior}" for fact in graph.facts)
    law_lines = "\n".join(f"{law.law_id}|{law.law_name}|{law.article}|{law.legal_element}" for law in laws)
    conflict_lines = "\n".join(f"{item.conflict_id}|{item.conflict_type}|{item.source_a}|{item.source_b}|{item.severity}" for item in conflicts)
    return (
        f"confirmed_case_type: {payload['confirmed_case_type']}\n\n"
        f"case_graph_facts:\n{fact_lines}\n\n"
        f"legal_matches:\n{law_lines}\n\n"
        f"conflicts:\n{conflict_lines}"
    )


def _reasoning_fallback(payload: dict[str, Any]) -> str:
    return ReasoningAgent().reason(payload)


def _facts_from_json(data: dict[str, Any], material: Material) -> list[Fact]:
    raw_facts = data.get("facts", [])
    if not isinstance(raw_facts, list):
        return []
    facts: list[Fact] = []
    for index, item in enumerate(raw_facts, start=1):
        if not isinstance(item, dict):
            continue
        facts.append(
            Fact(
                fact_id=str(item.get("fact_id") or f"F-{material.material_id}-TEXT-{index}"),
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=str(item.get("person", "")),
                behavior=str(item.get("behavior", "")),
                time=str(item.get("time", "")),
                location=str(item.get("location", "")),
                object=str(item.get("object", "")),
                confidence=float(item.get("confidence", 0.8) or 0.8),
            )
        )
    return facts or TextAgent()._extract_fallback(material)

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
                fallback=lambda: _planning_fallback(materials),
                parser=_case_type_suggestion_from_json,
            )
        joined = "\n".join(item.content for item in materials)
        if any(word in joined for word in ("故意伤害", "殴打", "轻伤", "骨折", "抱摔")):
            case_type = "故意伤害类案件"
        elif any(word in joined for word in ("门锁", "盗窃", "占有")):
            case_type = "盗窃类案件"
        else:
            case_type = "待人工判断案件"
        return CaseTypeSuggestion(
            suggested_case_types=[
                {
                    "case_type": case_type,
                    "confidence": 0.82 if case_type != "待人工判断案件" else 0.5,
                    "basis": ["demo 根据材料关键词生成建议，需人工确认"],
                    "requires_human_confirmation": True,
                }
            ]
        )


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
        person = _find_person(material.content)
        behavior = material.content.strip()
        return [
            Fact(
                fact_id=f"F-{material.material_id}-TEXT",
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=person,
                behavior=behavior,
                time=_find_time(material.content),
                location="鐜板満" if "鐜板満" in material.content else "",
                confidence=0.86,
            )
        ]


@dataclass
class PicAgent:
    name: str = "pic_agent"
    vision_tool: Any | None = None

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
        return [
            Fact(
                fact_id=f"F-{material.material_id}-PIC",
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=_find_person(content),
                behavior=f"图片内容：{content.strip()}",
                time=_find_time(content),
                location="现场" if "现场" in content else "",
                object="门锁" if "门锁" in content else "",
                confidence=confidence,
            )
        ]

@dataclass
class ReportImageAgent:
    name: str = "report_image_agent"
    legal_tool: LegalRetrievalTool | None = None
    vision_tool: Any | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        content = material.content
        if self.vision_tool is not None and _should_use_vision_tool(material):
            description = self.vision_tool.describe(material)
            content = _image_description_content(description)
        report_type = "监控研判报告" if any(word in content for word in ("监控", "研判")) else "法医检测报告"
        confidence = 0.93 if any(word in content for word in ("签章清晰", "结论", "报告", "鉴定意见", "轻伤")) else 0.78
        return [
            Fact(
                fact_id=f"F-{material.material_id}-REPORT",
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=_find_person(content),
                behavior=f"{report_type}结论：{content.strip()}",
                time=_find_time(content),
                location="现场附近" if "现场附近" in content else "",
                confidence=confidence,
            )
        ]

    def extract_group(self, group_id: str, image_paths: list[str]) -> list[Fact]:
        if self.vision_tool is None:
            content = f"Report image group pending Qwen vision: {group_id}"
        else:
            description = self.vision_tool.describe_group(group_id, image_paths)
            content = _image_description_content(description)
        material = Material(group_id, MaterialType.REPORT_IMAGE, content, source_path=";".join(image_paths))
        report_type = "report_image"
        confidence = 0.93 if any(word in content for word in ("结论", "报告", "鉴定意见", "轻伤")) else 0.78
        return [
            Fact(
                fact_id=f"F-{material.material_id}-REPORT",
                source_material_id=material.material_id,
                source_type=material.material_type.value,
                person=_find_person(content),
                behavior=f"{report_type}: {content.strip()}",
                time=_find_time(content),
                location="现场附近" if "现场附近" in content else "",
                confidence=confidence,
            )
        ]


@dataclass
class EvidenceGraphAgent:
    name: str = "case_graph_agent"
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(lambda facts: CaseGraph(facts=list(facts)))

    def build(self, facts: list[Fact]) -> CaseGraph:
        return self.runnable.invoke(facts)


CaseGraphAgent = EvidenceGraphAgent


@dataclass
class ConflictAgent:
    name: str = "conflict_agent"

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.detect)

    def detect(self, graph: EvidenceGraph) -> list[Conflict]:
        conflicts: list[Conflict] = []
        absent = [fact for fact in graph.facts if any(word in fact.behavior for word in ("没有到过现场", "在家"))]
        present = [fact for fact in graph.facts if any(word in fact.behavior for word in ("出现在现场", "在现场", "看见"))]
        for idx, left in enumerate(absent, start=1):
            for right in present:
                if left.fact_id != right.fact_id:
                    conflicts.append(
                        Conflict(
                            conflict_id=f"C-{idx}",
                            conflict_type="presence_conflict",
                            claim_a=left.behavior,
                            claim_b=right.behavior,
                            source_a=left.source_material_id,
                            source_b=right.source_material_id,
                            severity="high",
                        )
                    )
        return conflicts


@dataclass
class _LegacyRagLegalAgent:
    name: str = "rag_legal_agent"

    def __post_init__(self) -> None:
        self.runnable = RunnableLambda(self.retrieve)

    def retrieve(self, payload: dict[str, Any]) -> list[LegalMatch]:
        case_type = payload["confirmed_case_type"]
        graph: EvidenceGraph = payload["evidence_graph"]
        behavior = "；".join(fact.behavior for fact in graph.facts[:3])
        return [
            LegalMatch(
                law_id="L-DEMO-1",
                law_name="中华人民共和国刑法",
                article="第二百三十四条（demo 预置）",
                legal_element="故意伤害他人身体的，需结合伤情、行为、因果关系等证据审查。",
                matched_behavior=f"{case_type} / {behavior}",
                source="demo 预置法条片段，未实现 RAG 入库",
            )
        ]


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
        fact_lines = "\n".join(f"- {fact.person}：{fact.behavior}（来源 {fact.source_material_id}）" for fact in graph.facts)
        law_lines = "\n".join(f"- {law.law_name}{law.article}：{law.legal_element}" for law in laws)
        conflict_lines = "\n".join(f"- {item.conflict_type}：{item.source_a} 与 {item.source_b} 需人工核对" for item in conflicts)
        if not conflict_lines:
            conflict_lines = "- 暂未发现结构化规则可识别的冲突。"
        return (
            f"人工确认案件类型：{case_type}\n\n"
            f"现有证据显示：\n{fact_lines}\n\n"
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
