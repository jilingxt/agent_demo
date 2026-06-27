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
    ReviewResult,
)
from case_agent_demo.prompt_config import PromptLoader
from case_agent_demo.tools import LegalRetrievalTool, RagLegalAgent
from case_agent_demo.vision_tools import ImageEvidenceDescription


def _find_person(text: str) -> str:
    match = re.search(r"([\u4e00-\u9fa5]{2,3})(?:称|出现在|在|没有|参与)", text)
    if not match:
        return "未识别人员"
    person = match.group(1)
    if len(person) == 3 and person[0] in "年月日时分秒点第":
        return person[1:]
    return person


def _find_time(text: str) -> str:
    match = re.search(r"(\d{1,2}?(?:\d{1,2}?)?)", text)
    return match.group(1) if match else ""


def _should_use_vision_tool(material: Material) -> bool:
    content = material.content.strip()
    return bool(material.source_path and (not content or "Qwen" in content))


def _image_description_content(description: ImageEvidenceDescription) -> str:
    return description.to_material_content()

@dataclass
class PlanningAgent:
    name: str = "planning_agent"
    prompt: str = ""

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("planning_agent")
        self.runnable = RunnableLambda(self._suggest)

    def suggest(self, materials: list[Material]) -> CaseTypeSuggestion:
        return self.runnable.invoke(materials)

    def _suggest(self, materials: list[Material]) -> CaseTypeSuggestion:
        joined = "\n".join(item.content for item in materials)
        case_type = "盗窃类案件" if any(word in joined for word in ("门锁", "盗", "占有")) else "待人工判断案件"
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
    prompt: str = ""

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("text_agent")
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
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
                location="现场" if "现场" in material.content else "",
                confidence=0.86,
            )
        ]


@dataclass
class PicAgent:
    name: str = "pic_agent"
    prompt: str = ""
    vision_tool: Any | None = None

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("pic_agent_qwen")
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        content = material.content
        confidence = 0.9
        if self.vision_tool is not None and _should_use_vision_tool(material):
            description = self.vision_tool.describe(material)
            content = _image_description_content(description)
            confidence = description.confidence
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
    prompt: str = ""
    legal_tool: LegalRetrievalTool | None = None
    vision_tool: Any | None = None

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("report_image_agent")
        self.runnable = RunnableLambda(self.extract)

    def extract(self, material: Material) -> list[Fact]:
        content = material.content
        if self.vision_tool is not None and _should_use_vision_tool(material):
            description = self.vision_tool.describe(material)
            content = _image_description_content(description)
        report_type = "监控研判报告" if "监控" in content else "法医检测报告"
        confidence = 0.93 if any(word in content for word in ("签章清晰", "结论", "报告")) else 0.78
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

@dataclass
class EvidenceGraphAgent:
    name: str = "case_graph_agent"
    prompt: str = ""
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("evidence_graph_agent")
        self.runnable = RunnableLambda(lambda facts: CaseGraph(facts=list(facts)))

    def build(self, facts: list[Fact]) -> CaseGraph:
        return self.runnable.invoke(facts)


CaseGraphAgent = EvidenceGraphAgent


@dataclass
class ConflictAgent:
    name: str = "conflict_agent"
    prompt: str = ""

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("conflict_agent")
        self.runnable = RunnableLambda(self.detect)

    def detect(self, graph: EvidenceGraph) -> list[Conflict]:
        conflicts: list[Conflict] = []
        absent = [fact for fact in graph.facts if "没有到过现场" in fact.behavior or "在家" in fact.behavior]
        present = [fact for fact in graph.facts if "出现在现场" in fact.behavior or "看见" in fact.behavior]
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
                article="第二百六十四条（demo 预置）",
                legal_element="以非法占有为目的，秘密窃取公私财物等构成要件需结合证据审查。",
                matched_behavior=f"{case_type} / {behavior}",
                source="demo 预置法条片段，未实现 RAG 入库",
            )
        ]


@dataclass
class ReasoningAgent:
    name: str = "reasoning_agent"
    prompt: str = ""
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("reasoning_agent")
        self.runnable = RunnableLambda(self.reason)

    def retrieve_legal_matches(self, payload: dict[str, Any]) -> list[LegalMatch]:
        if self.legal_tool is None:
            return list(payload.get("legal_matches", []))
        return self.legal_tool.retrieve({**payload, "purpose": "reasoning_legal_basis"})

    def reason(self, payload: dict[str, Any]) -> str:
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
    prompt: str = ""
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("judge_agent")
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
    prompt: str = ""
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        if not self.prompt:
            self.prompt = PromptLoader().load("review_agent")
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
