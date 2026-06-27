# RAG Tool Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor demo legal retrieval from a standalone `RagLegalAgent` workflow node into a shared `LegalRetrievalTool` callable by selected agents, and document how to ingest legal texts later.

**Architecture:** Add a focused tool module for legal retrieval. Keep `LegalMatch` as the shared output contract, inject the tool into agents that need law lookup, and preserve a legacy `RagLegalAgent` wrapper for compatibility.

**Tech Stack:** Python dataclasses, LangChain `RunnableLambda`, `unittest`, existing `case_agent_demo` package.

---

### Task 1: Add Tests For RAG-As-Tool Behavior

**Files:**
- Modify: `F:\汇报\agent_demo\tests\test_workflow.py`
- Modify: `F:\汇报\agent_demo\tests\test_open_source_stack.py`

- [ ] Add tests asserting workflow exposes `legal_tool`, no longer records `rag_legal_agent` as an executed agent, and records `legal_retrieval_tool` usage.
- [ ] Add tests asserting Reasoning, Judge, and Review can receive tool-returned `LegalMatch` values.
- [ ] Run `python -m unittest discover -s tests -v` and verify the new tests fail before production code changes.

### Task 2: Implement Shared Legal Retrieval Tool

**Files:**
- Create: `F:\汇报\agent_demo\case_agent_demo\tools.py`
- Modify: `F:\汇报\agent_demo\case_agent_demo\agents.py`
- Modify: `F:\汇报\agent_demo\case_agent_demo\workflow.py`

- [ ] Move demo law retrieval logic into `LegalRetrievalTool.retrieve`.
- [ ] Add a legacy `RagLegalAgent` wrapper that delegates to `LegalRetrievalTool`.
- [ ] Inject `LegalRetrievalTool` into `ReportImageAgent`, `EvidenceGraphAgent`, `ReasoningAgent`, `JudgeAgent`, and `ReviewAgent`.
- [ ] Change `CaseWorkflow` so it no longer has a `rag_agent` field and no longer executes `rag_legal_agent` as a workflow node.
- [ ] Preserve `WorkflowResult.legal_matches` by using results produced through `ReasoningAgent`.

### Task 3: Update Documentation

**Files:**
- Modify: `F:\汇报\agent_demo\README.md`
- Modify: `F:\汇报\agent_demo\USER_GUIDE.md`
- Modify: `F:\汇报\agent_demo\CONFIGURATION_GUIDE.md`
- Modify: `F:\汇报\agent_demo\ARCHITECTURE_TECHNICAL.md`
- Create: `F:\汇报\agent_demo\LEGAL_INGESTION_GUIDE.md`

- [ ] Replace `RagLegalAgent` workflow-node wording with `LegalRetrievalTool`.
- [ ] Explain that demo retrieval is static/preloaded and production ingestion can later use LlamaIndex or LangChain Retriever.
- [ ] Add a legal text ingestion guide covering source collection, metadata, chunking, embedding, vector store, retrieval API, and Review audit checks.

### Task 4: Verify

**Files:**
- Modify: `F:\汇报\workflow-runs\20260627-105457-rag-tool-refactor\STATUS.md`
- Modify: `F:\汇报\workflow-runs\20260627-105457-rag-tool-refactor\reviews\review-log.md`

- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Record verification result in workflow status and review log.
