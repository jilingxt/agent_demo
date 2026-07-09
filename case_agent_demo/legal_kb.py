from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from case_agent_demo.domain_affinity import CaseDomainRouter, DomainAffinityIndexer
from case_agent_demo.models import DomainAffinity, EvidenceGraph, LegalChunk, LegalDocument, LegalMatch, LegalRAGResult


class LegalKnowledgeBaseTool:
    def __init__(self, root: str | Path = "legal_knowledge") -> None:
        self.root = Path(root)
        self.incoming_dir = self.root / "incoming"
        self.index_dir = self.root / "index"
        for folder in (self.incoming_dir, self.root / "active", self.root / "archived", self.root / "metadata", self.index_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.documents_path = self.index_dir / "documents.jsonl"
        self.chunks_path = self.index_dir / "chunks.jsonl"
        self.documents: dict[str, LegalDocument] = {}
        self.chunks: dict[str, LegalChunk] = {}
        self._load()

    def ingest_folder(self, folder: str | Path | None = None) -> list[LegalDocument]:
        source_folder = Path(folder) if folder is not None else self.incoming_dir
        docs: list[LegalDocument] = []
        for path in sorted(source_folder.glob("*")):
            if path.suffix.lower() in {".txt", ".md", ".jsonl"}:
                docs.append(self.ingest_document(path))
        return docs

    def ingest_document(
        self,
        file_path: str | Path,
        doc_type: str | None = None,
        metadata: dict | None = None,
    ) -> LegalDocument:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8-sig")
        document_id = _document_id(path, text)
        title = _title_from_text(path, text)
        document = LegalDocument(
            document_id=document_id,
            title=title,
            doc_type=doc_type or _doc_type(path),
            source_path=str(path),
            source=str(path),
            document_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            metadata=metadata or {},
        )
        chunks = _chunks_from_file(document, path, text)
        indexer = DomainAffinityIndexer()
        chunks = [replace(chunk, domain_affinities=indexer.score_chunk(chunk)) for chunk in chunks]
        document = replace(document, domain_affinities=indexer.score_document(document, chunks))
        self.documents[document.document_id] = document
        for chunk in chunks:
            self.chunks[chunk.chunk_id] = chunk
        self._save()
        return document

    def update_document(
        self,
        document_id: str,
        new_file_path: str | Path,
        metadata: dict | None = None,
    ) -> LegalDocument:
        if document_id in self.documents:
            old = self.documents[document_id]
            self.documents[document_id] = replace(old, effective_status="archived")
            for chunk_id, chunk in list(self.chunks.items()):
                if chunk.document_id == document_id:
                    self.chunks[chunk_id] = replace(chunk, effective_status="archived")
        return self.ingest_document(new_file_path, metadata=metadata)

    def delete_document(self, document_id: str, soft_delete: bool = True) -> None:
        if document_id not in self.documents:
            return
        if soft_delete:
            self.documents[document_id] = replace(self.documents[document_id], effective_status="deleted")
            for chunk_id, chunk in list(self.chunks.items()):
                if chunk.document_id == document_id:
                    self.chunks[chunk_id] = replace(chunk, effective_status="deleted")
        else:
            self.documents.pop(document_id, None)
            self.chunks = {chunk_id: chunk for chunk_id, chunk in self.chunks.items() if chunk.document_id != document_id}
        self._save()

    def reindex(self, document_id: str | None = None) -> None:
        self._save()

    def search(
        self,
        query: str,
        purpose: str = "legal_basis",
        doc_types: list[str] | None = None,
        domain_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> LegalRAGResult:
        query_tokens = _query_tokens(query)
        scored: list[LegalChunk] = []
        for chunk in self.chunks.values():
            if chunk.effective_status != "effective":
                continue
            if doc_types and chunk.doc_type not in doc_types:
                continue
            keyword_score = _keyword_score(chunk, query_tokens)
            domain_score = _domain_score(chunk, domain_ids or [])
            title_score = 1.0 if any(token and token in f"{chunk.title}{chunk.article}" for token in query_tokens) else 0.0
            final_score = 0.40 * keyword_score + 0.25 * domain_score + 0.20 * _doc_type_score(chunk.doc_type) + 0.15 * title_score
            if final_score > 0:
                scored.append(replace(chunk, score=round(final_score, 4)))
        scored.sort(key=lambda item: item.score, reverse=True)
        chunks = scored[:top_k]
        return LegalRAGResult(
            matches=[_chunk_to_match(chunk, query, purpose) for chunk in chunks],
            chunks=chunks,
            query=query,
            purpose=purpose,
            query_trace={"domain_ids": domain_ids or [], "tokens": query_tokens},
        )

    def retrieve_for_case(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        top_k: int = 8,
    ) -> LegalRAGResult:
        query = _query_from_graph(case_type, evidence_graph)
        domains = [item.domain_id for item in CaseDomainRouter().infer_domains(case_type, evidence_graph)[:4]]
        return self.search(query, purpose="legal_basis", domain_ids=domains, top_k=top_k)

    def retrieve_for_review(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        draft_report: str = "",
        top_k: int = 12,
    ) -> LegalRAGResult:
        review_domains = [
            "procedure_compliance",
            "evidence_review",
            "forensic_injury",
            "image_video_evidence",
            "statement_review",
            "identification",
            "supplementary_investigation",
            "report_boundary",
        ]
        query = f"{_query_from_graph(case_type, evidence_graph)} {draft_report}"
        return self.search(query, purpose="final_compliance_review", domain_ids=review_domains, top_k=top_k)

    def _load(self) -> None:
        self.documents = {doc.document_id: doc for doc in _read_documents(self.documents_path)}
        self.chunks = {chunk.chunk_id: chunk for chunk in _read_chunks(self.chunks_path)}

    def _save(self) -> None:
        _write_jsonl(self.documents_path, [asdict(item) for item in self.documents.values()])
        _write_jsonl(self.chunks_path, [asdict(item) for item in self.chunks.values()])


def _document_id(path: Path, text: str) -> str:
    return f"D-{hashlib.sha1((str(path) + text).encode('utf-8')).hexdigest()[:12]}"


def _title_from_text(path: Path, text: str) -> str:
    first = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "")
    return first[:80] or path.stem


def _doc_type(path: Path) -> str:
    return "jsonl_law_library" if path.suffix.lower() == ".jsonl" else "normative_file"


def _chunks_from_file(document: LegalDocument, path: Path, text: str) -> list[LegalChunk]:
    if path.suffix.lower() == ".jsonl":
        return _chunks_from_legacy_jsonl(document, text)
    parts = _split_articles(text)
    chunks: list[LegalChunk] = []
    for index, part in enumerate(parts, start=1):
        article = _article(part)
        chunks.append(
            LegalChunk(
                chunk_id=f"C-{document.document_id}-{index}",
                document_id=document.document_id,
                text=part,
                title=document.title,
                article=article,
                doc_type=document.doc_type,
            )
        )
    return chunks


def _chunks_from_legacy_jsonl(document: LegalDocument, text: str) -> list[LegalChunk]:
    chunks: list[LegalChunk] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        law = json.loads(line)
        chunk_id = str(law.get("law_id") or f"C-{document.document_id}-{index}")
        chunks.append(
            LegalChunk(
                chunk_id=chunk_id,
                document_id=document.document_id,
                text=str(law.get("text", "")),
                title=str(law.get("law_name", document.title)),
                article=str(law.get("article", "")),
                doc_type=document.doc_type,
                keywords=[str(item) for item in law.get("keywords", [])],
                legal_elements=[str(item) for item in law.get("legal_elements", [])],
                metadata={"source": law.get("source", "")},
            )
        )
    return chunks


def _split_articles(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"第[一二三四五六七八九十百千万零\d]+条", line) and current:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    if not chunks:
        chunks = [text]
    return chunks


def _article(text: str) -> str:
    match = re.search(r"(第[一二三四五六七八九十百千万零\d]+条)", text)
    return match.group(1) if match else ""


def _query_tokens(query: str) -> list[str]:
    return [token for token in re.split(r"[\s；，。、:：/]+", query) if token]


def _keyword_score(chunk: LegalChunk, tokens: list[str]) -> float:
    haystack = f"{chunk.title} {chunk.article} {chunk.text} {' '.join(chunk.keywords)} {' '.join(chunk.legal_elements)}"
    hits = sum(1 for token in tokens if token in haystack)
    return min(1.0, hits / max(1, min(4, len(tokens))))


def _domain_score(chunk: LegalChunk, domain_ids: list[str]) -> float:
    if not domain_ids:
        return 0.0
    scores = [item.score for item in chunk.domain_affinities if item.domain_id in domain_ids]
    return max(scores) if scores else 0.0


def _doc_type_score(doc_type: str) -> float:
    return 0.7 if doc_type else 0.4


def _query_from_graph(case_type: str, graph: EvidenceGraph) -> str:
    behavior = "；".join(fact.behavior for fact in graph.facts[:5])
    obj = "；".join(fact.object for fact in graph.facts[:5] if fact.object)
    return f"{case_type} {behavior} {obj}"


def _chunk_to_match(chunk: LegalChunk, query: str, purpose: str) -> LegalMatch:
    legal_element = "；".join(chunk.legal_elements) or chunk.text
    return LegalMatch(
        law_id=chunk.chunk_id,
        law_name=chunk.title,
        article=chunk.article,
        legal_element=legal_element,
        matched_behavior=query,
        source=f"legal_kb:{purpose}:{chunk.document_id}:{chunk.chunk_id}",
        effective_status=chunk.effective_status,
    )


def _read_documents(path: Path) -> list[LegalDocument]:
    return [LegalDocument(**_restore_domain_affinities(item)) for item in _read_jsonl(path)]


def _read_chunks(path: Path) -> list[LegalChunk]:
    return [LegalChunk(**_restore_domain_affinities(item)) for item in _read_jsonl(path)]


def _restore_domain_affinities(item: dict[str, Any]) -> dict[str, Any]:
    restored = dict(item)
    restored["domain_affinities"] = [
        affinity if isinstance(affinity, DomainAffinity) else DomainAffinity(**affinity)
        for affinity in restored.get("domain_affinities", [])
    ]
    return restored


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in items), encoding="utf-8")
