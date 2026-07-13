from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np

from case_agent_demo.domain_affinity import CaseDomainRouter, DomainAffinityIndexer
from case_agent_demo.legal_embeddings import (
    FastEmbedProvider,
    HashingEmbeddingProvider,
    cosine_similarity,
    lexical_terms,
)
from case_agent_demo.legal_parser import PageText, parse_legal_pages, read_legal_source
from case_agent_demo.models import (
    DomainAffinity,
    EvidenceAssertion,
    EvidenceGraph,
    LegalChunk,
    LegalDocument,
    LegalMatch,
    LegalRAGResult,
)


INDEX_VERSION = "legal-hybrid-rag-v1"
SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".jsonl"}
CANONICAL_DOC_TYPES = {
    "中华人民共和国刑法": "criminal_law",
    "中华人民共和国治安管理处罚法": "public_security_law",
    "中华人民共和国刑事诉讼法": "criminal_procedure_law",
}


class LegalKnowledgeBaseTool:
    def __init__(
        self,
        root: str | Path = "legal_knowledge",
        embedding_provider: HashingEmbeddingProvider | FastEmbedProvider | None = None,
    ) -> None:
        self.root = Path(root)
        self.incoming_dir = self.root / "incoming"
        self.index_dir = self.root / "index"
        for folder in (
            self.incoming_dir,
            self.root / "active",
            self.root / "archived",
            self.root / "metadata",
            self.index_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)
        self.database_path = self.index_dir / "legal_kb.sqlite3"
        self.manifest_path = self.root / "metadata" / "corpus_manifest.json"
        self._initialize_database()
        self.embedding_provider = embedding_provider or self._provider_from_index()
        self.documents: dict[str, LegalDocument] = {}
        self.chunks: dict[str, LegalChunk] = {}
        self._load()
        if self.documents and not self._provider_matches_index():
            self.reindex()

    def ingest_folder(self, folder: str | Path | None = None) -> list[LegalDocument]:
        source_folder = Path(folder) if folder is not None else self.incoming_dir
        return [
            self.ingest_document(path)
            for path in sorted(source_folder.glob("*"))
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ]

    def ingest_document(
        self,
        file_path: str | Path,
        doc_type: str | None = None,
        metadata: dict | None = None,
    ) -> LegalDocument:
        document, chunks, vectors = self._prepare_document(file_path, doc_type, metadata)
        existing = self.documents.get(document.document_id)
        if (
            existing
            and existing.document_hash == document.document_hash
            and existing.effective_status == "effective"
        ):
            self._write_manifest()
            return existing
        self._persist(document, chunks, vectors)
        return document

    def _prepare_document(
        self,
        file_path: str | Path,
        doc_type: str | None = None,
        metadata: dict | None = None,
        document_id_override: str | None = None,
    ) -> tuple[LegalDocument, list[LegalChunk], list[np.ndarray]]:
        path = Path(file_path).resolve()
        text, pages = read_legal_source(path)
        document_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        title = _title_from_text(path, text)
        document_id = document_id_override or _document_id(title, document_hash)
        inferred_metadata = _document_metadata(path, text, pages)
        inferred_metadata.update(metadata or {})
        document = LegalDocument(
            document_id=document_id,
            title=title,
            doc_type=CANONICAL_DOC_TYPES.get(title, doc_type or _doc_type(title, path)),
            source_path=str(path),
            source=str(path),
            version=str(inferred_metadata.get("version_label", "v1")),
            document_hash=document_hash,
            metadata=inferred_metadata,
        )
        chunks = _chunks_from_source(document, path, text, pages)
        if not chunks:
            raise ValueError(f"法律文件未解析出可索引内容：{path}")

        indexer = DomainAffinityIndexer()
        chunks = [replace(chunk, domain_affinities=indexer.score_chunk(chunk)) for chunk in chunks]
        document = replace(document, domain_affinities=indexer.score_document(document, chunks))
        vectors = self.embedding_provider.embed_documents([_embedding_text(chunk) for chunk in chunks])
        return document, chunks, vectors

    def update_document(
        self,
        document_id: str,
        new_file_path: str | Path,
        metadata: dict | None = None,
    ) -> LegalDocument:
        old = self.documents.get(document_id)
        if old is None:
            raise KeyError(f"法律文档不存在：{document_id}")
        next_metadata = dict(metadata or {})
        next_metadata.setdefault("supersedes_document_id", document_id)
        next_metadata.setdefault("version_group_id", old.metadata.get("version_group_id", old.title))
        document, chunks, vectors = self._prepare_document(
            new_file_path,
            doc_type=old.doc_type,
            metadata=next_metadata,
        )
        archive_id = document_id if document.document_id != document_id else None
        self._persist(document, chunks, vectors, archive_document_id=archive_id)
        return document

    def delete_document(self, document_id: str, soft_delete: bool = True) -> None:
        if document_id not in self.documents:
            return
        if soft_delete:
            self._set_document_status(document_id, "deleted")
            return
        with self._connect() as connection:
            chunk_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT chunk_id FROM chunks WHERE document_id = ?", (document_id,)
                )
            ]
            connection.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            connection.executemany("DELETE FROM chunk_fts WHERE chunk_id = ?", [(item,) for item in chunk_ids])
            connection.executemany("DELETE FROM embeddings WHERE chunk_id = ?", [(item,) for item in chunk_ids])
        self.documents.pop(document_id, None)
        self.chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self.chunks.items()
            if chunk.document_id != document_id
        }
        self._write_manifest()

    def reindex(self, document_id: str | None = None) -> None:
        selected = [
            document
            for document in self.documents.values()
            if document.effective_status == "effective"
            and (document_id is None or document.document_id == document_id)
        ]
        if document_id is not None and not selected:
            raise KeyError(f"法律文档不存在或未生效：{document_id}")
        prepared: list[tuple[LegalDocument, list[LegalChunk], list[np.ndarray]]] = []
        for document in selected:
            generated = {
                "version_label",
                "record_status",
                "legal_status",
                "jurisdiction",
                "legal_level",
                "source_file",
                "page_count",
                "effective_from",
            }
            metadata = {
                key: value for key, value in document.metadata.items() if key not in generated
            }
            prepared.append(
                self._prepare_document(
                    document.source_path,
                    doc_type=document.doc_type,
                    metadata=metadata,
                    document_id_override=document.document_id,
                )
            )
        self._persist_many(prepared)

    def search(
        self,
        query: str,
        purpose: str = "legal_basis",
        doc_types: list[str] | None = None,
        domain_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> LegalRAGResult:
        query = " ".join(query.split()).strip()
        if not query:
            return LegalRAGResult([], [], query, purpose, query_trace=self._trace(domain_ids or []))
        retrieval_query = _expand_query(query)

        active = {
            chunk_id: chunk
            for chunk_id, chunk in self.chunks.items()
            if chunk.effective_status == "effective"
            and (not doc_types or chunk.doc_type in doc_types)
        }
        query_terms = lexical_terms(retrieval_query)
        fts_ids = self._fts_candidates(query_terms, limit=max(50, top_k * 5))
        query_vector = self.embedding_provider.embed_query(retrieval_query)
        dense_scores = self._dense_scores(query_vector, active)
        dense_ids = {
            chunk_id
            for chunk_id, _ in sorted(dense_scores.items(), key=lambda item: item[1], reverse=True)[
                : max(50, top_k * 5)
            ]
        }

        scored: list[LegalChunk] = []
        score_trace: dict[str, dict[str, float]] = {}
        for chunk_id in fts_ids | dense_ids:
            chunk = active.get(chunk_id)
            if chunk is None:
                continue
            if not _passes_legal_context_gate(query, chunk, purpose):
                continue
            lexical_hits = _lexical_hits(query_terms, chunk)
            lexical_score = _lexical_score(query_terms, lexical_hits)
            dense_score = max(0.0, dense_scores.get(chunk_id, 0.0))
            concept_score = _concept_score(query, chunk)
            if not _is_relevant(
                lexical_score,
                lexical_hits,
                dense_score,
                concept_score,
                self.embedding_provider.semantic,
            ):
                continue
            domain_score = _domain_score(chunk, domain_ids or [])
            exact_score = _exact_score(retrieval_query, chunk)
            type_score = _purpose_type_score(purpose, chunk.doc_type)
            final_score = min(
                1.0,
                0.30 * lexical_score
                + 0.32 * dense_score
                + 0.20 * concept_score
                + 0.08 * domain_score
                + 0.07 * exact_score
                + 0.03 * type_score,
            )
            components = {
                "lexical": round(lexical_score, 4),
                "lexical_hits": lexical_hits,
                "dense": round(dense_score, 4),
                "concept": round(concept_score, 4),
                "domain": round(domain_score, 4),
                "exact": round(exact_score, 4),
                "doc_type": round(type_score, 4),
                "final": round(final_score, 4),
            }
            score_trace[chunk_id] = components
            scored.append(
                replace(
                    chunk,
                    score=components["final"],
                    metadata={**chunk.metadata, "retrieval_scores": components},
                )
            )
        scored.sort(key=lambda item: (item.score, _article_sort_key(item.article)), reverse=True)
        chunks = scored[:top_k]
        trace = self._trace(domain_ids or [])
        trace.update(
            {
                "query_terms": query_terms[:80],
                "expanded_query": retrieval_query,
                "candidate_counts": {"fts": len(fts_ids), "dense": len(dense_ids)},
                "scores": {chunk.chunk_id: score_trace[chunk.chunk_id] for chunk in chunks},
                "relevance_gate": {
                    "lexical_min": 0.12,
                    "semantic_dense_min": 0.55,
                    "legal_concept_min": 0.5,
                },
            }
        )
        return LegalRAGResult(
            matches=[_chunk_to_match(chunk, query, purpose) for chunk in chunks],
            chunks=chunks,
            query=query,
            purpose=purpose,
            query_trace=trace,
        )

    def retrieve_for_case(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        top_k: int = 8,
        claim_assessments: list[Any] | None = None,
    ) -> LegalRAGResult:
        query = _query_from_graph(case_type, evidence_graph, claim_assessments)
        domains = [
            item.domain_id
            for item in CaseDomainRouter().infer_domains(case_type, evidence_graph)[:6]
        ]
        result = self.search(
            query,
            purpose="legal_basis",
            doc_types=["criminal_law", "public_security_law", "jsonl_law_library"],
            domain_ids=domains,
            top_k=top_k,
        )
        result.query_trace["retrieval_plan"] = [
            "substantive_criminal_law",
            "public_security_law",
            "administrative_criminal_boundary",
        ]
        return result

    def retrieve_for_allegations(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        assertions: list[EvidenceAssertion] | None = None,
        top_k: int = 12,
    ) -> LegalRAGResult:
        query = _query_from_allegations(case_type, evidence_graph, assertions or [])
        domains = [
            item.domain_id
            for item in CaseDomainRouter().infer_domains(case_type, evidence_graph)[:8]
        ]
        result = self.search(
            query,
            purpose="allegation_discovery",
            doc_types=["criminal_law", "public_security_law", "jsonl_law_library"],
            domain_ids=domains,
            top_k=top_k,
        )
        result.query_trace["retrieval_plan"] = [
            "alleged_facts_high_recall",
            "substantive_candidate_provisions",
            "human_legal_classification_required",
        ]
        return result

    def retrieve_for_review(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        draft_report: str = "",
        top_k: int = 12,
        claim_assessments: list[Any] | None = None,
    ) -> LegalRAGResult:
        routed = [
            item.domain_id
            for item in CaseDomainRouter().infer_domains(case_type, evidence_graph)[:6]
        ]
        review_domains = list(
            dict.fromkeys(
                [
                    *routed,
                    "public_security_punishment",
                    "procedure_compliance",
                    "evidence_review",
                    "supplementary_investigation",
                ]
            )
        )
        base = _query_from_graph(case_type, evidence_graph, claim_assessments)
        query = (
            f"{base} 治安管理处罚 刑事责任 违法行为 处罚程序 调查 决定 执行 "
            "证据审查 鉴定意见 视听资料 询问笔录 真实性 合法性 关联性 "
            f"{draft_report[:800]}"
        )
        result = self.search(
            query,
            purpose="final_compliance_review",
            domain_ids=review_domains,
            top_k=top_k,
        )
        result.query_trace["retrieval_plan"] = [
            "substantive_basis",
            "public_security_boundary",
            "criminal_procedure_and_evidence_review",
        ]
        result.query_trace["missing_corpus_scopes"] = [
            "forensic_appraisal_standards",
        ]
        return result

    def _provider_from_index(self):
        with self._connect() as connection:
            values = dict(connection.execute("SELECT key, value FROM index_meta"))
        if values.get("embedding_backend") == "fastembed":
            return FastEmbedProvider(
                model_name=values.get("embedding_model", "BAAI/bge-small-zh-v1.5"),
                cache_dir=str(self.root / "models"),
            )
        dimensions = int(values.get("embedding_dimensions", 384))
        return HashingEmbeddingProvider(dimensions=dimensions)

    def _provider_matches_index(self) -> bool:
        with self._connect() as connection:
            values = dict(connection.execute("SELECT key, value FROM index_meta"))
            distributions = list(
                connection.execute(
                    """
                    SELECT model, dimensions, length(vector) AS byte_length, count(*) AS row_count
                    FROM embeddings
                    GROUP BY model, dimensions, length(vector)
                    """
                )
            )
            chunk_count = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
            embedding_count = connection.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        if not values.get("embedding_backend"):
            return chunk_count == 0 and embedding_count == 0
        metadata_matches = (
            values.get("embedding_backend") == self.embedding_provider.backend
            and values.get("embedding_model") == self.embedding_provider.model_name
            and int(values.get("embedding_dimensions", 0))
            == self.embedding_provider.dimensions
        )
        rows_match = (
            chunk_count == embedding_count
            and len(distributions) == 1
            and distributions[0]["model"] == self.embedding_provider.model_name
            and distributions[0]["dimensions"] == self.embedding_provider.dimensions
            and distributions[0]["byte_length"] == self.embedding_provider.dimensions * 4
            and distributions[0]["row_count"] == chunk_count
        )
        return metadata_matches and rows_match

    def _initialize_database(self) -> None:
        with self._connect(initialize=False) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(document_id)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
                    chunk_id UNINDEXED,
                    search_text,
                    tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    vector BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connect(self, initialize: bool = True):
        del initialize
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _load(self) -> None:
        with self._connect() as connection:
            self.documents = {
                row["document_id"]: _document_from_payload(row["payload"])
                for row in connection.execute("SELECT document_id, payload FROM documents")
            }
            self.chunks = {
                row["chunk_id"]: _chunk_from_payload(row["payload"])
                for row in connection.execute("SELECT chunk_id, payload FROM chunks")
            }

    def _persist(
        self,
        document: LegalDocument,
        chunks: list[LegalChunk],
        vectors: list[np.ndarray],
        archive_document_id: str | None = None,
    ) -> None:
        self._persist_many(
            [(document, chunks, vectors)],
            archive_document_id=archive_document_id,
        )

    def _persist_many(
        self,
        prepared: list[tuple[LegalDocument, list[LegalChunk], list[np.ndarray]]],
        archive_document_id: str | None = None,
    ) -> None:
        if any(len(chunks) != len(vectors) for _, chunks, vectors in prepared):
            raise ValueError("条款数量与向量数量不一致")
        archived_document = None
        archived_chunks: dict[str, LegalChunk] = {}
        if archive_document_id:
            archived_document = replace(
                self.documents[archive_document_id], effective_status="archived"
            )
            archived_chunks = {
                chunk_id: replace(chunk, effective_status="archived")
                for chunk_id, chunk in self.chunks.items()
                if chunk.document_id == archive_document_id
            }
        with self._connect() as connection:
            if archived_document is not None:
                connection.execute(
                    "UPDATE documents SET payload = ? WHERE document_id = ?",
                    (_json_payload(archived_document), archive_document_id),
                )
                connection.executemany(
                    "UPDATE chunks SET payload = ? WHERE chunk_id = ?",
                    [
                        (_json_payload(chunk), chunk_id)
                        for chunk_id, chunk in archived_chunks.items()
                    ],
                )
            for document, chunks, vectors in prepared:
                self._persist_rows(connection, document, chunks, vectors)
            meta = {
                "index_version": INDEX_VERSION,
                "embedding_backend": self.embedding_provider.backend,
                "embedding_model": self.embedding_provider.model_name,
                "embedding_dimensions": str(self.embedding_provider.dimensions),
            }
            connection.executemany(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES (?, ?)", meta.items()
            )
        if archived_document is not None:
            self.documents[archive_document_id] = archived_document
            self.chunks.update(archived_chunks)
        for document, chunks, _ in prepared:
            self.chunks = {
                chunk_id: chunk
                for chunk_id, chunk in self.chunks.items()
                if chunk.document_id != document.document_id
            }
            self.documents[document.document_id] = document
            self.chunks.update({chunk.chunk_id: chunk for chunk in chunks})
        self._write_manifest()

    def _persist_rows(
        self,
        connection: sqlite3.Connection,
        document: LegalDocument,
        chunks: list[LegalChunk],
        vectors: list[np.ndarray],
    ) -> None:
        old_ids = [
            row[0]
            for row in connection.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = ?", (document.document_id,)
            )
        ]
        connection.executemany("DELETE FROM chunk_fts WHERE chunk_id = ?", [(item,) for item in old_ids])
        connection.executemany("DELETE FROM embeddings WHERE chunk_id = ?", [(item,) for item in old_ids])
        connection.execute("DELETE FROM chunks WHERE document_id = ?", (document.document_id,))
        connection.execute(
            "INSERT OR REPLACE INTO documents(document_id, payload) VALUES (?, ?)",
            (document.document_id, _json_payload(document)),
        )
        for chunk, vector in zip(chunks, vectors):
            connection.execute(
                "INSERT INTO chunks(chunk_id, document_id, payload) VALUES (?, ?, ?)",
                (chunk.chunk_id, chunk.document_id, _json_payload(chunk)),
            )
            connection.execute(
                "INSERT INTO chunk_fts(chunk_id, search_text) VALUES (?, ?)",
                (chunk.chunk_id, " ".join(lexical_terms(_embedding_text(chunk)))),
            )
            array = np.asarray(vector, dtype=np.float32)
            connection.execute(
                "INSERT INTO embeddings(chunk_id, model, dimensions, vector) VALUES (?, ?, ?, ?)",
                (chunk.chunk_id, self.embedding_provider.model_name, array.size, array.tobytes()),
            )

    def _set_document_status(self, document_id: str, status: str) -> None:
        document = replace(self.documents[document_id], effective_status=status)
        affected = {
            chunk_id: replace(chunk, effective_status=status)
            for chunk_id, chunk in self.chunks.items()
            if chunk.document_id == document_id
        }
        with self._connect() as connection:
            connection.execute(
                "UPDATE documents SET payload = ? WHERE document_id = ?",
                (_json_payload(document), document_id),
            )
            connection.executemany(
                "UPDATE chunks SET payload = ? WHERE chunk_id = ?",
                [(_json_payload(chunk), chunk_id) for chunk_id, chunk in affected.items()],
            )
        self.documents[document_id] = document
        self.chunks.update(affected)
        self._write_manifest()

    def _write_manifest(self) -> None:
        payload = {
            "index_version": INDEX_VERSION,
            "embedding_backend": self.embedding_provider.backend,
            "embedding_model": self.embedding_provider.model_name,
            "documents": [
                {
                    "document_id": document.document_id,
                    "title": document.title,
                    "doc_type": document.doc_type,
                    "version": document.version,
                    "document_hash": document.document_hash,
                    "effective_status": document.effective_status,
                    "source_path": document.source_path,
                    "chunk_count": sum(
                        chunk.document_id == document.document_id
                        for chunk in self.chunks.values()
                    ),
                    "metadata": document.metadata,
                }
                for document in sorted(self.documents.values(), key=lambda item: item.title)
            ],
        }
        temporary = self.manifest_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.manifest_path)

    def _fts_candidates(self, terms: list[str], limit: int) -> set[str]:
        if not terms:
            return set()
        query = " OR ".join(f'"{term}"' for term in terms[:80])
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT ?",
                (query, limit),
            )
            return {row[0] for row in rows}

    def _dense_scores(
        self,
        query_vector: np.ndarray,
        active: dict[str, LegalChunk],
    ) -> dict[str, float]:
        if not active:
            return {}
        placeholders = ",".join("?" for _ in active)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT chunk_id, dimensions, vector FROM embeddings WHERE chunk_id IN ({placeholders})",
                tuple(active),
            )
            return {
                row["chunk_id"]: cosine_similarity(
                    query_vector,
                    np.frombuffer(row["vector"], dtype=np.float32, count=row["dimensions"]),
                )
                for row in rows
            }

    def _trace(self, domain_ids: list[str]) -> dict[str, Any]:
        return {
            "index_version": INDEX_VERSION,
            "embedding_backend": self.embedding_provider.backend,
            "embedding_model": self.embedding_provider.model_name,
            "semantic_embeddings": self.embedding_provider.semantic,
            "domain_ids": domain_ids,
            "corpus": [
                {
                    "document_id": document.document_id,
                    "title": document.title,
                    "version": document.version,
                    "document_hash": document.document_hash,
                    "effective_status": document.effective_status,
                }
                for document in self.documents.values()
                if document.effective_status == "effective"
            ],
        }


def _chunks_from_source(
    document: LegalDocument,
    path: Path,
    text: str,
    pages: list[PageText],
) -> list[LegalChunk]:
    if path.suffix.lower() == ".jsonl":
        return _chunks_from_legacy_jsonl(document, text)
    articles = parse_legal_pages(pages)
    if not articles:
        return [
            LegalChunk(
                chunk_id=f"C-{document.document_id}-1",
                document_id=document.document_id,
                text=text.strip(),
                title=document.title,
                doc_type=document.doc_type,
                metadata={"source_page_start": 1, "source_page_end": len(pages)},
            )
        ]
    return [
        LegalChunk(
            chunk_id=f"C-{document.document_id}-{hashlib.sha1(item.article.encode('utf-8')).hexdigest()[:10]}",
            document_id=document.document_id,
            text=item.text,
            title=document.title,
            article=item.article,
            doc_type=document.doc_type,
            metadata={
                "part": item.part,
                "chapter": item.chapter,
                "section": item.section,
                "source_page_start": item.page_start,
                "source_page_end": item.page_end,
                "source_path": document.source_path,
                "document_hash": document.document_hash,
            },
        )
        for item in articles
    ]


def _chunks_from_legacy_jsonl(document: LegalDocument, text: str) -> list[LegalChunk]:
    chunks: list[LegalChunk] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        law = json.loads(line)
        chunks.append(
            LegalChunk(
                chunk_id=str(law.get("law_id") or f"C-{document.document_id}-{index}"),
                document_id=document.document_id,
                text=str(law.get("text", "")),
                title=str(law.get("law_name", document.title)),
                article=str(law.get("article", "")),
                doc_type=document.doc_type,
                keywords=[str(item) for item in law.get("keywords", [])],
                legal_elements=[str(item) for item in law.get("legal_elements", [])],
                metadata={"source": law.get("source", ""), "source_page_start": 1, "source_page_end": 1},
            )
        )
    return chunks


def _document_id(title: str, document_hash: str) -> str:
    return f"D-{hashlib.sha1(f'{title}:{document_hash}'.encode('utf-8')).hexdigest()[:12]}"


def _title_from_text(path: Path, text: str) -> str:
    for canonical in (
        "中华人民共和国治安管理处罚法",
        "中华人民共和国刑事诉讼法",
        "中华人民共和国刑法",
    ):
        if canonical in text[:3000]:
            return canonical
    first = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "")
    return first[:80] or path.stem


def _doc_type(title: str, path: Path) -> str:
    if title in CANONICAL_DOC_TYPES:
        return CANONICAL_DOC_TYPES[title]
    return "jsonl_law_library" if path.suffix.lower() == ".jsonl" else "normative_file"


def _document_metadata(path: Path, text: str, pages: list[PageText]) -> dict[str, Any]:
    version = "v1"
    compact = re.sub(r"\s+", "", text[:5000])
    revisions = re.findall(r"(20\d{2})年(?=.{0,120}?(修正|修订))", compact)
    if revisions:
        year, mode = max(revisions, key=lambda item: int(item[0]))
        version = f"{year}年{mode}"
    effective = re.search(r"自(20\d{2})年(\d{1,2})月(\d{1,2})日起施行", text[:5000])
    return {
        "version_label": version,
        "record_status": "active",
        "legal_status": "effective",
        "jurisdiction": "CN",
        "legal_level": "law",
        "source_file": path.name,
        "page_count": len(pages),
        "effective_from": (
            f"{effective.group(1)}-{int(effective.group(2)):02d}-{int(effective.group(3)):02d}"
            if effective
            else ""
        ),
    }


def _embedding_text(chunk: LegalChunk) -> str:
    headings = " ".join(
        str(chunk.metadata.get(key, "")) for key in ("part", "chapter", "section")
    )
    return f"{chunk.title} {headings} {chunk.article} {chunk.text}"


def _lexical_hits(query_terms: list[str], chunk: LegalChunk) -> int:
    return len(set(query_terms) & set(lexical_terms(_embedding_text(chunk))))


def _lexical_score(query_terms: list[str], hits: int) -> float:
    if not query_terms:
        return 0.0
    return min(1.0, hits / max(1, min(12, len(set(query_terms)))))


def _exact_score(query: str, chunk: LegalChunk) -> float:
    haystack = _embedding_text(chunk)
    phrases = [item for item in re.split(r"[\s，。；、]+", query) if len(item) >= 2]
    return 1.0 if any(phrase in haystack for phrase in phrases) else 0.0


def _is_relevant(
    lexical_score: float,
    lexical_hits: int,
    dense_score: float,
    concept_score: float,
    semantic: bool,
) -> bool:
    return (
        concept_score >= 0.5
        or (lexical_hits >= 2 and lexical_score >= 0.12)
        or (semantic and dense_score >= 0.55)
    )


_QUERY_EXPANSIONS = (
    (("盗窃", "窃取", "偷拿"), "盗窃 公私财物 非法占有"),
    (("殴打", "伤害", "轻伤", "重伤"), "殴打他人 故意伤害他人身体"),
    (("毁坏", "损坏", "砸坏"), "故意毁坏公私财物"),
    (("扰乱", "公共场所秩序"), "扰乱公共秩序 聚众扰乱"),
    (("诈骗", "骗取", "虚构", "隐瞒真相", "信以为真", "错误认识"), "诈骗公私财物 虚构事实 隐瞒真相"),
    (("抢夺", "抢劫"), "抢夺公私财物 抢劫"),
)


def _expand_query(query: str) -> str:
    additions = [
        expansion
        for triggers, expansion in _QUERY_EXPANSIONS
        if any(trigger in query for trigger in triggers)
    ]
    return " ".join([query, *additions])


def _concept_score(query: str, chunk: LegalChunk) -> float:
    text = chunk.text.replace(" ", "")
    if any(term in query for term in ("盗窃", "窃取", "偷拿")):
        if "盗窃公私财物" in text:
            return 1.0
        if "盗窃" in text:
            return 0.8
    if any(term in query for term in ("殴打", "伤害", "轻伤", "重伤")):
        if "故意伤害他人身体" in text:
            return 1.0
        if "殴打他人的，或者故意伤害他人身体" in text:
            return 1.0
        if _query_has_any(query, ("寻衅滋事", "随意殴打", "结伙斗殴", "起哄闹事")) and (
            "随意殴打他人" in text or "结伙斗殴" in text
        ):
            return 1.0
    if any(term in query for term in ("毁坏", "损坏", "砸坏")):
        if "毁坏公私财物" in text or "损毁" in text:
            return 1.0
    if "扰乱" in query and ("扰乱公共秩序" in text or "扰乱" in text):
        return 1.0
    if _query_has_any(query, ("投放危险物质", "放火", "爆炸", "公共安全")) and _query_has_any(
        text, ("投放毒害性", "放火、决水、爆炸", "危害公共安全", "危险物质")
    ):
        return 1.0
    if any(term in query for term in ("诈骗", "骗取", "虚构", "隐瞒真相", "信以为真", "错误认识")) and "诈骗" in text:
        return 1.0
    if any(term in query for term in ("抢夺", "抢劫")) and ("抢夺" in text or "抢劫" in text):
        return 1.0
    return 0.0


def _query_has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _passes_legal_context_gate(query: str, chunk: LegalChunk, purpose: str) -> bool:
    text = chunk.text.replace(" ", "")
    query_families = _query_behavior_families(query)
    chunk_families = _chunk_primary_families(chunk)
    if purpose == "legal_basis" and query_families and _is_supplied_statute_chunk(chunk):
        if not chunk_families.intersection(query_families):
            return False
    exclusive_contexts = (
        (("寻衅滋事", "随意殴打他人", "结伙斗殴"), ("寻衅滋事", "随意殴打", "结伙斗殴", "起哄闹事", "破坏社会秩序")),
        (("绑架他人", "劫持人质"), ("绑架", "劫持", "人质", "勒索财物")),
        (("偷越国（边）境", "偷越国(边)境"), ("偷越国（边）境", "偷越国(边)境", "偷越边境", "组织偷越")),
        (("写恐吓信", "威胁他人人身安全"), ("威胁", "恐吓", "恐吓信")),
        (("虚假证明、鉴定", "意图陷害他人或者隐匿罪证"), ("伪证", "虚假证明", "虚假鉴定", "隐匿罪证")),
        (("信用卡诈骗", "保险诈骗", "侵犯商业秘密"), ("信用卡", "保险诈骗", "商业秘密")),
    )
    for chunk_markers, required_query_terms in exclusive_contexts:
        if _query_has_any(text, chunk_markers) and not _query_has_any(query, required_query_terms):
            return False
    if "致人重伤、死亡或者使公私财产遭受重大损失" in text and not _query_has_any(
        query,
        ("重伤", "死亡", "重大损失", "严重后果"),
    ):
        return False

    if purpose == "legal_basis" and _is_procedural_chunk(text) and not _query_has_any(
        query,
        ("程序", "调查", "取证", "询问", "鉴定程序", "证据审查", "扣押", "检查"),
    ):
        return False
    return True


def _query_behavior_families(query: str) -> set[str]:
    positive = re.sub(
        r"(?:不构成|不涉及|排除|未发现)(?:寻衅滋事|绑架|威胁|伪证|偷越国（边）境|偷越国\(边\)境)",
        "",
        query,
    )
    rules = (
        ("personal_injury", ("故意伤害", "殴打", "抱摔", "轻伤", "重伤", "骨折")),
        ("theft", ("盗窃", "窃取", "偷拿", "偷走", "非法占有")),
        ("deception_disposition", ("诈骗", "骗取", "虚构", "隐瞒真相", "错误认识", "信以为真", "转账")),
        ("property_damage", ("毁坏", "损坏", "砸坏", "摔坏", "损毁")),
        ("public_place_order", ("车站", "机场", "商场", "公园", "公共场所秩序", "公共交通工具")),
        ("social_order", ("工作不能正常进行", "生产不能正常进行", "营业不能正常进行", "聚众扰乱社会秩序")),
        ("provocation", ("寻衅滋事", "随意殴打", "结伙斗殴", "起哄闹事", "强拿硬要")),
        ("public_safety", ("危害公共安全", "投放危险物质", "放火", "爆炸", "不特定多数人")),
        ("kidnapping", ("绑架", "劫持人质")),
        ("border_crossing", ("偷越国（边）境", "偷越国(边)境", "偷越边境")),
        ("threat", ("威胁他人人身安全", "写恐吓信", "恐吓他人")),
        ("false_testimony", ("伪证", "虚假证明", "虚假鉴定", "隐匿罪证")),
    )
    return {
        family
        for family, terms in rules
        if _query_has_any(positive, terms)
    }


def _chunk_primary_families(chunk: LegalChunk) -> set[str]:
    text = re.sub(r"\s+", "", chunk.text)
    rules = (
        ("personal_injury", ("故意伤害他人身体的", "殴打他人的，或者故意伤害他人身体的")),
        ("theft", ("盗窃公私财物，", "盗窃、诈骗、哄抢、抢夺或者敲诈勒索的")),
        ("deception_disposition", ("诈骗公私财物", "诈骗的")),
        ("property_damage", ("故意毁坏公私财物，", "故意损毁公私财物的")),
        ("public_place_order", ("聚众扰乱车站", "扰乱车站、港口、码头、机场、商场、公园", "扰乱公共交通工具上的秩序")),
        ("social_order", ("聚众扰乱社会秩序", "扰乱机关、团体、企业、事业单位秩序")),
        ("provocation", ("有下列寻衅滋事行为", "结伙斗殴或者随意殴打他人的")),
        ("public_safety", ("放火、决水、爆炸以及投放", "违反国家规定，制造、买卖、储存、运输、邮寄、携带、使用、提供、处置爆炸性")),
        ("kidnapping", ("以勒索财物为目的绑架他人的",)),
        ("border_crossing", ("组织他人偷越国（边）境", "运送他人偷越国（边）境")),
        ("threat", ("写恐吓信或者以其他方法威胁他人人身安全",)),
        ("false_testimony", ("故意作虚假证明、鉴定、记录、翻译",)),
    )
    return {
        family
        for family, phrases in rules
        if _query_has_any(text, phrases)
    }


def _is_supplied_statute_chunk(chunk: LegalChunk) -> bool:
    source_path = str(chunk.metadata.get("source_path", "")).replace("/", "\\").casefold()
    return (
        chunk.title in {
            "中华人民共和国刑法",
            "中华人民共和国治安管理处罚法",
            "中华人民共和国刑事诉讼法",
        }
        and source_path.endswith(".pdf")
        and "law_db" in source_path
    )


def _is_procedural_chunk(text: str) -> bool:
    markers = (
        "办理治安案件",
        "为了查明案件事实",
        "作为治安案件的证据使用",
        "需要作为证据的物品",
        "人民警察办理治安案件",
        "询问查证",
    )
    return _query_has_any(text, markers)


def _domain_score(chunk: LegalChunk, domain_ids: list[str]) -> float:
    scores = [item.score for item in chunk.domain_affinities if item.domain_id in domain_ids]
    return max(scores) if scores else 0.0


def _purpose_type_score(purpose: str, doc_type: str) -> float:
    if purpose in {"evidence_review", "procedure_compliance", "final_compliance_review"}:
        if doc_type == "criminal_procedure_law":
            return 1.0
    if "review" in purpose and doc_type == "public_security_law":
        return 1.0
    return 0.7 if doc_type in {
        "criminal_law",
        "public_security_law",
        "criminal_procedure_law",
    } else 0.4


def _query_from_graph(
    case_type: str,
    graph: EvidenceGraph,
    claim_assessments: list[Any] | None = None,
) -> str:
    assessments_by_id = {
        item.claim_id: item for item in (claim_assessments or [])
    }
    predicate_terms = {
        "deceptive_representation": "虚构事实 隐瞒真相 欺骗 诈骗公私财物",
        "mistaken_belief": "信以为真 产生错误认识",
        "property_disposition": "转账 付款 交付财物 财产处分",
        "property_loss": "财产损失 未返还",
        "violence": "殴打他人 伤害他人身体",
        "injury_exists": "人身损伤",
        "injury_consequence": "人身损伤",
        "injury_grade": "伤情鉴定 轻伤 重伤",
        "taking_property": "盗窃 公私财物 非法占有",
        "prior_possession": "财物原占有",
        "possession_transfer": "财物转移占有",
        "property_damage": "故意损毁公私财物",
        "damage_exists": "财物损坏结果",
        "public_order_conduct": "扰乱公共秩序",
        "public_context": "公共场所秩序",
        "operational_impact": "工作生产营业交通受到影响",
        "persistence_or_group": "聚众 持续实施",
        "hazardous_conduct": "危险行为 危害公共安全",
        "dangerous_object_or_condition": "危险物质 危险状态",
        "exposure": "不特定多数人 公共安全",
        "control_failure": "危险失去控制",
        "causation": "行为与结果因果关系",
    }
    parts = [case_type]
    seen_predicates: set[str] = set()
    supported_claims = [
        claim
        for claim in graph.claims
        if claim.status == "active"
        and _claim_is_retrieval_supported(claim, assessments_by_id.get(claim.claim_id))
    ]
    for claim in supported_claims:
        if claim.behavior_type in seen_predicates:
            continue
        term = predicate_terms.get(claim.behavior_type)
        if term:
            parts.append(term)
            seen_predicates.add(claim.behavior_type)

    salient_terms = (
        "轻伤二级", "轻伤", "重伤", "骨折", "鉴定意见", "殴打", "抱摔", "推搡",
        "盗窃", "窃取", "拿走", "手机", "现金", "财物",
        "损坏", "毁坏", "砸坏", "车辆",
        "扰乱秩序", "公共场所", "聚众", "通行中断", "停止营业",
        "放火", "爆炸", "投放危险物质", "不特定多数人",
        "寻衅滋事", "随意殴打", "结伙斗殴", "威胁", "绑架", "偷越国（边）境",
    )
    supported_node_ids = {
        node_id
        for claim in supported_claims
        for node_id in claim.supporting_node_ids
    }
    active_text = " ".join(
        f"{node.behavior} {node.object}"
        for node in graph.nodes
        if node.status == "active"
        and node.node_type == "fact"
        and (not graph.claims or node.node_id in supported_node_ids)
    )
    parts.extend(term for term in salient_terms if term in active_text)
    if len(parts) == 1:
        parts.extend(f"{fact.behavior} {fact.object}" for fact in graph.facts[:6])
    return " ".join(dict.fromkeys(parts))[:1200]


def _query_from_allegations(
    case_type: str,
    graph: EvidenceGraph,
    assertions: list[EvidenceAssertion],
) -> str:
    nodes = {node.node_id: node for node in graph.nodes}
    parts = [case_type]
    for assertion in assertions:
        if assertion.assertion_role != "allegation" or assertion.stance != "affirm":
            continue
        node = nodes.get(assertion.node_id)
        if node is not None:
            parts.append(f"{node.summary} {node.object}")
        parts.append(
            " ".join(
                value
                for value in (
                    assertion.predicate,
                    assertion.actor,
                    assertion.target_person,
                    assertion.object,
                )
                if value
            )
        )
    if len(parts) == 1:
        parts.extend(f"{fact.behavior} {fact.object}" for fact in graph.facts[:8])
    return " ".join(dict.fromkeys(item for item in parts if item))[:1600]


def _claim_is_retrieval_supported(claim: Any, assessment: Any | None) -> bool:
    if assessment is not None:
        if assessment.status in {"supported", "authority_anchored"}:
            return True
        return assessment.status == "bayesian_derived" and float(assessment.support_index) >= 0.5
    profile = getattr(claim, "confidence_profile", None)
    if profile is None:
        return bool(claim.supporting_node_ids) and not claim.opposing_node_ids
    return profile.label in {"有一定印证", "权威材料支持", "多源较强印证"}


def _chunk_to_match(chunk: LegalChunk, query: str, purpose: str) -> LegalMatch:
    legal_element = "；".join(chunk.legal_elements) or chunk.text
    page = chunk.metadata.get("source_page_start", "")
    return LegalMatch(
        law_id=chunk.chunk_id,
        law_name=chunk.title,
        article=chunk.article,
        legal_element=legal_element,
        matched_behavior=query,
        source=f"legal_kb:{purpose}:{chunk.document_id}:{chunk.chunk_id}:p{page}",
        effective_status=chunk.effective_status,
    )


def _json_payload(value: object) -> str:
    return json.dumps(asdict(value), ensure_ascii=False, separators=(",", ":"))


def _document_from_payload(payload: str) -> LegalDocument:
    values = _restore_domain_affinities(json.loads(payload))
    return LegalDocument(**values)


def _chunk_from_payload(payload: str) -> LegalChunk:
    values = _restore_domain_affinities(json.loads(payload))
    return LegalChunk(**values)


def _restore_domain_affinities(item: dict[str, Any]) -> dict[str, Any]:
    restored = dict(item)
    restored["domain_affinities"] = [
        affinity if isinstance(affinity, DomainAffinity) else DomainAffinity(**affinity)
        for affinity in restored.get("domain_affinities", [])
    ]
    return restored


def _article_sort_key(article: str) -> int:
    match = re.search(r"\d+", article)
    return int(match.group()) if match else 0
