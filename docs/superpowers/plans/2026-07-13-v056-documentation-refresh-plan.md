# v0.56 Documentation Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all explanatory documentation accurately describe the current v0.56 implementation while preserving clearly labeled v0.51 history.

**Architecture:** Derive one authoritative fact sheet from code, configuration, the legal corpus manifest, and verification output. Apply it through four audience-specific documents, then run contradiction and command checks.

**Tech Stack:** Markdown, Mermaid, PowerShell, Python, pytest

## Global Constraints

- Preserve clearly labeled v0.51 historical content.
- Remove or rewrite stale current-state statements instead of merely appending another correction.
- Do not change runtime code or user-authored unrelated content.
- Keep legal conclusions and Bayesian support indices clearly separated.

---

### Task 1: Build the current-state fact sheet

**Files:**
- Inspect: `pyproject.toml`
- Inspect: `config/bayesian_models/registry.json`
- Inspect: `legal_knowledge/metadata/corpus_manifest.json`
- Inspect: `case_agent_demo/workflow.py`

- [ ] Verify version, relationship component IDs, legal corpus size, workflow input, EvidenceBook fields, and abstention reasons.
- [ ] Record contradictions found in the four target documents.

### Task 2: Refresh overview documents

**Files:**
- Modify: `README.md`
- Modify: `项目介绍.md`

- [ ] Replace stale current-state descriptions with one coherent v0.56 overview.
- [ ] Add the case-neutral workflow, EvidenceBook output, RAG scope, safety boundaries, and current verification status.

### Task 3: Refresh operational documents

**Files:**
- Modify: `技术手册.md`
- Modify: `用户手册.md`

- [ ] Document exact data contracts, call flow, parameter sources, relation component selection, abstention behavior, and RAG pipeline.
- [ ] Document material preparation, commands, output interpretation, human review, and troubleshooting.

### Task 4: Verify documentation

**Files:**
- Review: `README.md`
- Review: `项目介绍.md`
- Review: `技术手册.md`
- Review: `用户手册.md`

- [ ] Search for stale five-case, two-law, manual-confirmation, old-test-count, and static-RAG claims.
- [ ] Run `git diff --check` and `python -m pytest -q -p no:cacheprovider`.
- [ ] Update workflow-run audit and review records with observed results.
