from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableLambda

from case_agent_demo.models import EvidenceGraph, LegalChunk, LegalMatch, LegalRAGResult
from case_agent_demo.legal_kb import LegalKnowledgeBaseTool


DEFAULT_LEGAL_LIBRARY = Path("legal_library") / "laws.jsonl"


@dataclass
class LegalRetrievalTool:
    """Unified legal retrieval with hybrid-KB and static-library fallback."""

    name: str = "legal_retrieval_tool"
    library_path: str | Path | None = DEFAULT_LEGAL_LIBRARY
    max_matches: int = 5
    legal_kb: LegalKnowledgeBaseTool | None = None

    def __post_init__(self) -> None:
        self.library_path = Path(self.library_path) if self.library_path else None
        self.runnable = RunnableLambda(self.retrieve)

    def retrieve(self, payload: dict[str, Any]) -> list[LegalMatch]:
        return self.retrieve_result(payload).matches

    def retrieve_result(self, payload: dict[str, Any]) -> LegalRAGResult:
        case_type = payload.get("confirmed_case_type") or payload.get("case_type") or "unknown_case_type"
        graph: EvidenceGraph | None = payload.get("evidence_graph") or payload.get("case_graph")
        behaviors = payload.get("behaviors")
        if behaviors is None and graph is not None:
            behaviors = [fact.behavior for fact in graph.facts[:3]]
        behavior_text = "；".join(str(item) for item in behaviors or [])
        purpose = payload.get("purpose", "legal_basis_lookup")

        if self.legal_kb is not None and graph is not None:
            if purpose == "allegation_discovery":
                result = self.legal_kb.retrieve_for_allegations(
                    case_type,
                    graph,
                    assertions=payload.get("assertions"),
                )
            elif "review" in purpose or "procedure" in purpose:
                result = self.legal_kb.retrieve_for_review(
                    case_type,
                    graph,
                    str(payload.get("draft_report", "")),
                    claim_assessments=payload.get("claim_assessments"),
                )
            else:
                result = self.legal_kb.retrieve_for_case(
                    case_type,
                    graph,
                    claim_assessments=payload.get("claim_assessments"),
                )
            if result.matches and result.chunks:
                return result

        matches = self._retrieve_from_static_library(case_type, behavior_text, purpose)
        if not matches:
            return LegalRAGResult(
                matches=[],
                chunks=[],
                query=f"{case_type} {behavior_text}".strip(),
                purpose=purpose,
                query_trace={
                    "fallback": "static_law_library",
                    "retrieval_miss": True,
                },
            )
        chunks = [
            LegalChunk(
                chunk_id=match.law_id,
                document_id=f"static:{match.law_name}",
                text=match.legal_element,
                title=match.law_name,
                article=match.article,
                doc_type="static_law_library",
                metadata={"source": match.source, "fallback": True},
            )
            for match in matches
        ]
        return LegalRAGResult(
            matches=matches,
            chunks=chunks,
            query=f"{case_type} {behavior_text}".strip(),
            purpose=purpose,
            query_trace={"fallback": "static_law_library"},
        )

    def _retrieve_from_static_library(self, case_type: str, behavior_text: str, purpose: str) -> list[LegalMatch]:
        if self.library_path is None or not self.library_path.exists():
            return []

        scored: list[tuple[int, int, dict[str, Any]]] = []
        query_text = f"{case_type} {behavior_text}".lower()
        for index, law in enumerate(_read_jsonl(self.library_path)):
            score = _score_law(law, case_type, query_text)
            if _should_include_law(law, case_type, query_text, score):
                scored.append((score, -index, law))

        scored.sort(reverse=True)
        return [
            _law_to_match(law, case_type, behavior_text, purpose)
            for _, _, law in scored[: self.max_matches]
        ]

@dataclass
class RagLegalAgent:
    """Legacy wrapper kept for old imports; new code should use LegalRetrievalTool."""

    name: str = "rag_legal_agent"
    legal_tool: LegalRetrievalTool | None = None

    def __post_init__(self) -> None:
        if self.legal_tool is None:
            self.legal_tool = LegalRetrievalTool()
        self.runnable = RunnableLambda(self.retrieve)

    def retrieve(self, payload: dict[str, Any]) -> list[LegalMatch]:
        return self.legal_tool.retrieve(payload)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    laws: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        laws.append(json.loads(line))
    return laws


def _score_law(law: dict[str, Any], case_type: str, query_text: str) -> int:
    score = 0
    case_types = [str(item) for item in law.get("case_types", [])]
    if any(item and item in case_type for item in case_types):
        score += 4
    for keyword in law.get("keywords", []):
        if str(keyword).lower() in query_text:
            score += 2
    for element in law.get("legal_elements", []):
        if str(element).lower() in query_text:
            score += 1
    law_text = str(law.get("text", "")).lower()
    if law_text and any(token in law_text for token in query_text.split()):
        score += 1
    return score


def _should_include_law(law: dict[str, Any], case_type: str, query_text: str, score: int) -> bool:
    if score <= 0:
        return False
    case_types = [str(item) for item in law.get("case_types", [])]
    case_type_matches = any(item and item in case_type for item in case_types)
    if case_type_matches:
        return score >= 2

    law_id = str(law.get("law_id", "")).lower()
    if "criminal_law_264" in law_id:
        theft_strong_terms = ("盗窃", "偷", "窃取", "拿走", "非法占有", "秘密窃取", "扒窃", "入户盗窃")
        return any(term in query_text for term in theft_strong_terms)

    if _has_property_damage_context(query_text) and _law_has_any(law, ("毁坏", "损坏", "摔坏", "砸坏")):
        return True

    strong_hits = 0
    generic_terms = {"手机", "财物", "物品", "现场", "人员"}
    for keyword in law.get("keywords", []):
        keyword_text = str(keyword).lower()
        if keyword_text and keyword_text not in generic_terms and keyword_text in query_text:
            strong_hits += 1
    for element in law.get("legal_elements", []):
        element_text = str(element).lower()
        if element_text and element_text not in generic_terms and element_text in query_text:
            strong_hits += 1
    return strong_hits >= 1 and score >= 2


def _law_has_any(law: dict[str, Any], terms: tuple[str, ...]) -> bool:
    haystack = " ".join(
        [
            str(law.get("text", "")),
            " ".join(str(item) for item in law.get("keywords", [])),
            " ".join(str(item) for item in law.get("legal_elements", [])),
        ]
    )
    return any(term in haystack for term in terms)


def _has_property_damage_context(query_text: str) -> bool:
    return any(term in query_text for term in ("毁坏", "损坏", "摔坏", "砸坏", "屏幕损坏", "裂开"))


def _law_to_match(law: dict[str, Any], case_type: str, behavior_text: str, purpose: str) -> LegalMatch:
    legal_elements = law.get("legal_elements") or []
    if isinstance(legal_elements, list) and legal_elements:
        legal_element = "；".join(str(item) for item in legal_elements)
    else:
        legal_element = str(law.get("text", ""))

    source = str(law.get("source", "static_law_library"))
    law_id = str(law.get("law_id", "unknown_law"))
    return LegalMatch(
        law_id=law_id,
        law_name=str(law.get("law_name", "")),
        article=str(law.get("article", "")),
        legal_element=legal_element,
        matched_behavior=f"{case_type} / {behavior_text}",
        source=f"legal_retrieval_tool:{purpose}:{source}:{law_id}",
        effective_status=str(law.get("effective_status", "effective")),
    )
