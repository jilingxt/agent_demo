# General Bayesian Evidence Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace case-specific Bayesian routing with a reusable, equal-priority model registry and deliver a governed Excel template for collecting calibration statistics.

**Architecture:** `BayesianEvidenceTool` selects one or more JSON models from a registry using case domains and Claim predicates, delegates deterministic evaluation to the existing engine, and returns versioned traces plus derived claims. `EvidenceReasoningEngine` remains the workflow-facing facade. A generated workbook and Markdown guide define the offline data required to estimate observation, extraction, dependency, CPD, and authority parameters.

**Tech Stack:** Python 3.11, dataclasses, JSON, existing Bayesian engine, openpyxl for workbook generation, pytest.

## Global Constraints

- Preserve existing public workflow APIs and legacy confidence fields.
- No case family receives a hard-coded routing priority.
- Do not output guilt or punishment probability.
- Do not learn legal thresholds or authority scope from role truth rates.
- All model outputs must include version, parameter hash, and calibration status.
- Preserve user-owned untracked `law_DB/` and `测试用例/`.

---

### Task 1: Model Registry And General Tool

**Files:**
- Create: `case_agent_demo/bayesian_tool.py`
- Create: `config/bayesian_models/registry.json`
- Test: `tests/test_bayesian_tool.py`

**Interfaces:**
- Consumes: `case_domains`, `EvidenceClaim[]`, `ClaimAssessment[]`.
- Produces: `BayesianModelRegistry.select(...)` and `BayesianEvidenceTool.evaluate(...)`.

- [ ] Write failing tests for equal-priority selection, multi-model selection, unknown cases, audit metadata, and missing model validation.
- [ ] Run `python -m pytest tests/test_bayesian_tool.py -q` and confirm failure because the module is absent.
- [ ] Implement the minimal registry loader, predicate/domain selector, input mapper, and tool result dataclasses.
- [ ] Re-run focused tests and commit.

### Task 2: Peer Case-Family Models

**Files:**
- Create: `config/bayesian_models/conduct_result_v1.json`
- Create: `config/bayesian_models/property_taking_v1.json`
- Create: `config/bayesian_models/public_order_v1.json`
- Create: `config/bayesian_models/public_safety_v1.json`
- Create: `config/bayesian_models/status_duty_v1.json`
- Create: `config/legal_elements/case_family_elements.json`
- Modify: `config/bayesian_models/registry.json`
- Test: `tests/test_bayesian_case_families.py`

**Interfaces:**
- Consumes: registry entries and normalized predicates.
- Produces: five validated model families with equal priority and legal-element metadata.

- [ ] Write failing tests that load every registered model and verify all derived nodes move in the expected direction.
- [ ] Run the focused tests and confirm missing files fail.
- [ ] Add minimal expert-prior JSON specifications and legal-element taxonomy.
- [ ] Re-run focused tests and commit.

### Task 3: Workflow Integration And Generic Review

**Files:**
- Modify: `case_agent_demo/evidence_reasoning_engine.py`
- Modify: `case_agent_demo/final_conflict_agent.py`
- Modify: `case_agent_demo/models.py`
- Test: `tests/test_general_bayesian_integration.py`
- Modify: existing Bayesian integration tests as required for the new peer model IDs.

**Interfaces:**
- Consumes: subjective Claim assessments and case-domain inference.
- Produces: compatible `EvidenceReasoningResult`, generic derived claims, and generic missing-element/derived-result challenges.

- [ ] Write failing tests proving personal injury, property taking, and public order use the same Tool path and no case-name special branch is required.
- [ ] Run focused tests and confirm the old hard-coded router fails the new expectations.
- [ ] Delegate model selection to `BayesianEvidenceTool`, append generic derived claims, and replace injury-specific final-review gating with derived-predicate rules.
- [ ] Re-run focused and regression tests and commit.

### Task 4: Statistical Workbook And Guide

**Files:**
- Create: `scripts/generate_bayesian_statistics_workbook.py`
- Create: `docs/statistics/bayesian_parameter_collection_template.xlsx`
- Create: `docs/statistics/BAYESIAN_PARAMETER_COLLECTION_GUIDE.md`
- Modify: `pyproject.toml`
- Test: `tests/test_statistics_workbook.py`

**Interfaces:**
- Produces: reproducible Excel workbook and field-level collection guide.

- [ ] Write a failing workbook contract test for required sheets, headers, formulas, validation, and freeze panes.
- [ ] Run the focused test and confirm the workbook/generator is absent.
- [ ] Add `openpyxl` as a documentation optional dependency, implement the generator, and generate the workbook.
- [ ] Write the Markdown guide with formulas, label rules, governance, privacy, and offline publication steps.
- [ ] Re-run focused tests and commit.

### Task 5: Verification And Merge

**Files:**
- Modify: workflow-run status, task, memory, and review files only.

**Interfaces:**
- Produces: reviewed commits merged locally to `main` without pushing.

- [ ] Run `python -m pytest tests -q` and record the exact count.
- [ ] Run `python -m compileall -q case_agent_demo scripts`.
- [ ] Regenerate the workbook and verify a clean artifact diff.
- [ ] Run `git diff --check`, inspect all changed files, and verify no `law_DB/` or `测试用例/` path is staged.
- [ ] Merge locally to `main`, rerun verification, and preserve the remote unchanged.
