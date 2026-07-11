# Bayesian Evidence Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scope-limited authority anchors, subjective evidence fusion, and a small Bayesian dependency model while preserving the current v0.51 APIs.

**Architecture:** Existing facts and graph nodes are normalized into assertions. Claims are fused by independent source group, authority rules are applied to technical predicates, and a JSON-defined Bayesian model derives causation. A facade maps the new output back to existing claim confidence fields.

**Tech Stack:** Python 3.11 standard library, dataclasses, JSON, unittest, existing LangChain Core integration.

## Global Constraints

- Keep the current package layout and old public entry points.
- Do not add a Bayesian framework dependency.
- Do not migrate any component to Dify.
- Treat all numeric outputs as uncalibrated evidence-support assessments.
- Preserve user-owned untracked files.

---

### Task 1: Structured Assertions And Claims

**Files:**
- Modify: `case_agent_demo/models.py`
- Create: `case_agent_demo/evidence_reasoning.py`
- Test: `tests/test_evidence_reasoning_models.py`

**Interfaces:**
- Consumes: `EvidenceGraph` and `EvidenceNode`.
- Produces: `EvidenceAssertion`, `EvidenceClaim`, `ClaimOpinion`, `ClaimAssessment`, and `AssertionNormalizer.normalize_graph(graph)`.

- [ ] Write tests that construct metadata-rich nodes and assert actor/predicate/stance grouping, including ambiguous assertions.
- [ ] Run `python -m unittest tests.test_evidence_reasoning_models -v` and verify imports or assertions fail because the new API is absent.
- [ ] Add the dataclasses and the smallest normalizer/claim builder that satisfies those tests while preserving old fields.
- [ ] Re-run the focused tests and the existing confidence tests.

### Task 2: Quality And Subjective Evidence Fusion

**Files:**
- Modify: `case_agent_demo/evidence_reasoning.py`
- Modify: `case_agent_demo/confidence.py`
- Test: `tests/test_subjective_evidence.py`

**Interfaces:**
- Consumes: assertions grouped into claims.
- Produces: `EvidenceQualityEvaluator.evaluate(assertion, claim)`, `SubjectiveEvidenceEngine.evaluate(claim, assertions)`, and compatible `ConfidenceProfile` values.

- [ ] Write tests for no evidence, independent supporting groups, duplicate origins, direct denial, and lack of memory.
- [ ] Run the focused test and verify the new engine is missing or returns the old behavior.
- [ ] Implement weighted geometric quality, max-per-source-group aggregation, Beta-style opinion values, and assessment classification.
- [ ] Make `ConfidenceEngine` delegate to the new engine without changing its method signatures.
- [ ] Re-run focused and existing confidence tests.

### Task 3: Authority Anchors

**Files:**
- Modify: `case_agent_demo/evidence_reasoning.py`
- Create: `config/authority_rules.json`
- Test: `tests/test_authority_reasoning.py`

**Interfaces:**
- Consumes: authority metadata on assertions and ordinary claim opinions.
- Produces: `AuthorityValidator.validate(assertion)` and authority-aware `ClaimAssessment`.

- [ ] Write tests showing a verified forensic injury-grade report establishes only the injury-grade claim, ordinary denial does not defeat it, and a conflicting reappraisal contests it.
- [ ] Run the focused test and verify failure before implementation.
- [ ] Implement explicit validation, predicate scope, anchor evidence conversion, and defeater handling.
- [ ] Re-run the focused tests.

### Task 4: Versioned Bayesian Inference

**Files:**
- Create: `case_agent_demo/bayesian_engine.py`
- Create: `config/bayesian_models/intentional_injury_v1.json`
- Test: `tests/test_bayesian_engine.py`

**Interfaces:**
- Consumes: JSON model specs and soft evidence values.
- Produces: `BayesianInferenceEngine.infer(soft_evidence)` with node posterior values and model audit metadata.

- [ ] Write tests for logistic causation increase, alternative-cause decrease, invalid model rejection, and no backward upgrade of violence.
- [ ] Run the focused test and verify failure because the module is absent.
- [ ] Implement JSON loading, validation, topological evaluation, logistic/noisy-or/prior nodes, and SHA-256 parameter hashing.
- [ ] Re-run the focused tests.

### Task 5: Unified Engine And Workflow Review

**Files:**
- Modify: `case_agent_demo/evidence_reasoning.py`
- Modify: `case_agent_demo/workflow.py`
- Modify: `case_agent_demo/final_conflict_agent.py`
- Modify: `case_agent_demo/agents.py`
- Modify: `case_agent_demo/models.py`
- Test: `tests/test_workflow_bayesian_reasoning.py`

**Interfaces:**
- Consumes: graph, confirmed case type, and optional authority verification metadata.
- Produces: `EvidenceReasoningEngine.evaluate(...) -> EvidenceReasoningResult`, workflow result fields, report assessment summaries, and grounded validation issues.

- [ ] Write an integration test for contested violence plus authoritative injury grade and unresolved causation.
- [ ] Run the focused test and verify expected fields/issues are absent.
- [ ] Wire the unified engine into `CaseWorkflow`, pass assessment summaries into report generation, and update final conflict rules.
- [ ] Re-run the integration test and all existing tests.

### Task 6: Verification And Version Management

**Files:**
- Modify: workflow-run status/review records only.

**Interfaces:**
- Consumes: completed feature diff.
- Produces: reviewed commits ready to merge into `main`.

- [ ] Run `python -m unittest discover -s tests -v` and record the exact test count.
- [ ] Run `python -m compileall -q case_agent_demo` and verify exit code 0.
- [ ] Review `git diff --check`, `git status --short`, and the full feature diff.
- [ ] Commit coherent implementation checkpoints and merge the feature branch into `main` without staging `测试用例/`.
