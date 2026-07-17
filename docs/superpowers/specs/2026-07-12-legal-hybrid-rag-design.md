# Legal Hybrid RAG Design

## Goal

Replace the static-law-only retrieval path with a local, traceable hybrid RAG tailored to evidence-claim analysis, and index the two laws in `law_DB/`.

## Architecture

The source PDFs remain immutable. A loader extracts page text, a legal parser creates article-level chunks with chapter, article and page metadata, and SQLite stores document metadata, chunks, FTS5 terms and dense vectors. Retrieval merges exact-term and dense candidates, then reranks by case domain, purpose, legal status and document type behind a relevance gate.

The embedding provider is replaceable. The preferred provider is local `BAAI/bge-small-zh-v1.5`; deterministic hashing remains an explicit degraded fallback so ingestion and tests still work without downloading a model. Query and index metadata always record which provider produced the vectors.

## Retrieval Flow

Case retrieval builds queries from case type, evidence nodes and claim assessments. Review retrieval issues separate substantive-law and public-security-boundary queries. Domain affinity and document type may reorder relevant candidates, but cannot make an otherwise irrelevant chunk eligible.

Every result carries document id, chunk id, law name, article, source path, source page, source hash, retrieval component scores and index version. Reasoning and final review use the same service and fallback policy.

## Scope

This iteration indexes the Criminal Law and Public Security Administration Punishments Law supplied by the user. It does not claim coverage of criminal procedure, evidence rules, appraisal standards or local discretion standards. Missing corpus coverage is exposed in the retrieval trace.

## Error Handling

Unreadable/scanned PDFs fail ingestion with a clear error rather than silently creating empty documents. Re-ingesting an unchanged hash is idempotent. Updating a document archives the old record and replaces its chunks atomically.

## Verification

Tests cover article parsing, PDF metadata, idempotent ingestion, FTS relevance gates, dense contribution, cross-law retrieval, unrelated-query rejection and compatibility with the existing workflow.
