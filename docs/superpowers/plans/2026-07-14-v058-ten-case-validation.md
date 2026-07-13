# v0.58 Ten-Case Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible ten-case synthetic corpus from five Criminal Law provisions and five Public Security Administration Punishments Law provisions, use it to verify and generically improve semantic evidence reasoning, and release the reconciled project as v0.58.0.

**Architecture:** Corpus generation is a development-time tool, isolated from runtime inference. Golden semantic assertions drive deterministic downstream acceptance through `SemanticFixtureRuntime`; a separate live-Agent runner records model deviations without restoring keyword inference. Production fixes are limited to shared semantic, Claim, Bayesian-selection, RAG, validation, and reporting contracts.

**Tech Stack:** Python 3.11+, pytest, standard library, python-docx and Pillow as optional `casegen` dependencies, existing LangChain Core runtime, existing SQLite/FTS5 legal index.

## Global Constraints

- Use random seed `58` and independently sample five provisions from each law.
- Preserve the approved final sample: Criminal Law Articles 353, 185, 189, 429, 186; Public Security Administration Punishments Law Articles 51, 52, 31, 50, 83.
- Record rejection of Criminal Law Article 383 and its replacement by Article 186.
- Every generated artifact must visibly contain `合成测试材料，仅用于系统验证，不对应真实人员、单位或案件`.
- Never copy personal data, institutions, QR codes, identifiers, addresses, or case numbers from reference files.
- Do not delete or replace existing prompts; only make generic schema clarifications when live-Agent deviations prove they are necessary.
- Do not restore keyword-based case-fact inference or add branches on corpus ID, article number, offense name, person, location, or case-specific prose.
- A legal retrieval candidate is not a fact, offense finding, guilt finding, or punishment decision.
- Bayesian safe abstention is a valid expected outcome when registered inputs are insufficient.
- Set the release version to `0.58.0` only after ten-case deterministic acceptance and the existing regression suite pass.

---

## File Map

- `scripts/v058_case_catalog.py`: approved provision/case definitions and reusable synthetic-data banner.
- `scripts/sample_v058_provisions.py`: reproducible SQLite sampling and rejection manifest.
- `scripts/generate_v058_cases.py`: DOCX, PNG, JSON, and golden-contract generation.
- `scripts/run_v058_live_agent_acceptance.py`: configured DeepSeek/Qwen integration runner and deviation report.
- `tests/v058_case_helpers.py`: package discovery, manifest loading, and golden semantic runtime construction.
- `tests/test_v058_sampling.py`: reproducibility and rejection tests.
- `tests/test_v058_case_generation.py`: artifact, banner, anonymization, and image-readability tests.
- `tests/test_v058_case_acceptance.py`: ten-case deterministic workflow acceptance.
- `tests/test_v058_live_agent_runner.py`: offline runner behavior and unavailable-model reporting.
- `测试用例/v058随机条文/`: generated ten-case corpus plus `sampling_manifest.json`.
- Existing runtime files are modified only when a failing generic acceptance test demonstrates a shared defect.
- `README.md`, `项目介绍.md`, `技术手册.md`, `用户手册.md`, `pyproject.toml`: v0.58 release documentation and version.

### Task 1: Reproducible Provision Sampling

**Files:**
- Create: `scripts/v058_case_catalog.py`
- Create: `scripts/sample_v058_provisions.py`
- Create: `tests/test_v058_sampling.py`

**Interfaces:**
- Consumes: `legal_knowledge/index/legal_kb.sqlite3` tables `documents` and `chunks`.
- Produces: `sample_provisions(db_path: Path, seed: int = 58) -> dict[str, object]` and JSON-serializable sampling manifest.

- [ ] **Step 1: Write the failing reproducibility test**

```python
def test_seed_58_reproduces_approved_sample():
    manifest = sample_provisions(ROOT / "legal_knowledge/index/legal_kb.sqlite3", seed=58)
    assert [item["article"] for item in manifest["accepted"]["criminal_law"]] == ["第三百五十三条", "第一百八十五条", "第一百八十九条", "第四百二十九条", "第一百八十六条"]
    assert [item["article"] for item in manifest["accepted"]["public_security_law"]] == ["第五十一条", "第五十二条", "第三十一条", "第五十条", "第八十三条"]
    assert manifest["rejected"] == [{"law": "criminal_law", "article": "第三百八十三条", "reason": "pure_penalty_provision", "replacement": "第一百八十六条"}]
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `python -m pytest tests/test_v058_sampling.py -q`

Expected: FAIL because `scripts.sample_v058_provisions` does not exist.

- [ ] **Step 3: Implement the sampler with explicit pool filters**

```python
def sample_provisions(db_path: Path, seed: int = 58) -> dict[str, object]:
    criminal = _load_pool(db_path, law="中华人民共和国刑法", metadata_key="part", metadata_value="第二编 分则")
    public_security = _load_pool(db_path, law="中华人民共和国治安管理处罚法", metadata_key="chapter", metadata_value="第三章 违反治安管理的行为和处罚")
    accepted_criminal, rejected = _sample_with_replacements(criminal, random.Random(seed), count=5)
    accepted_public, _ = _sample_with_replacements(public_security, random.Random(seed), count=5)
    return {"seed": seed, "accepted": {"criminal_law": accepted_criminal, "public_security_law": accepted_public}, "rejected": rejected}
```

The rejection predicate accepts only provisions containing independently testable prohibited conduct. Article 383 is recorded as `pure_penalty_provision`; all candidates and replacement positions are included in `draw_trace`.

- [ ] **Step 4: Run sampling tests and confirm GREEN**

Run: `python -m pytest tests/test_v058_sampling.py -q`

Expected: all sampling tests pass and two invocations produce byte-equivalent manifests after canonical JSON serialization.

- [ ] **Step 5: Commit the isolated sampler files**

```powershell
git add scripts/v058_case_catalog.py scripts/sample_v058_provisions.py tests/test_v058_sampling.py
git commit -m "test: add reproducible v0.58 legal sampling"
```

### Task 2: Synthetic Case Package Generator

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/generate_v058_cases.py`
- Create: `tests/test_v058_case_generation.py`
- Generate: `测试用例/v058随机条文/`

**Interfaces:**
- Consumes: catalog constants and sampling manifest from Task 1.
- Produces: `generate_corpus(output_root: Path, overwrite: bool = False) -> list[Path]` and ten complete case directories.

- [ ] **Step 1: Write failing package-contract tests**

```python
def test_generator_creates_ten_complete_anonymized_packages(tmp_path):
    cases = generate_corpus(tmp_path)
    assert len(cases) == 10
    for case_dir in cases:
        assert (case_dir / "case.json").is_file()
        assert (case_dir / "sampling.json").is_file()
        assert list((case_dir / "statements").glob("*.docx"))
        assert list((case_dir / "reports").glob("*.docx"))
        assert (case_dir / "expected/semantic_assertions.json").is_file()
        assert (case_dir / "expected/expected_outcome.json").is_file()
        assert SYNTHETIC_BANNER in extract_docx_text(next((case_dir / "statements").glob("*.docx")))
```

- [ ] **Step 2: Run the generator tests and confirm RED**

Run: `python -m pytest tests/test_v058_case_generation.py -q`

Expected: FAIL because `generate_corpus` does not exist.

- [ ] **Step 3: Add minimal case-generation dependencies**

Add to `pyproject.toml`:

```toml
casegen = [
  "python-docx>=1.1,<2",
  "Pillow>=10,<13"
]
```

- [ ] **Step 4: Implement deterministic DOCX and PNG generation**

```python
def generate_corpus(output_root: Path, overwrite: bool = False) -> list[Path]:
    manifest = sample_provisions(DEFAULT_DB, seed=58)
    _write_json(output_root / "sampling_manifest.json", manifest)
    generated = []
    for case in CASE_CATALOG:
        case_dir = output_root / f"{case.corpus_id}_{case.short_name}"
        _prepare_case_directory(case_dir, overwrite=overwrite)
        _write_case_json(case_dir, case)
        for statement in case.statements:
            _write_statement_docx(case_dir / "statements" / statement.filename, case, statement)
        for report in case.reports:
            docx_path = case_dir / "reports" / report.filename
            _write_report_docx(docx_path, case, report)
            if report.render_image:
                _render_report_png(case_dir / "report_images" / f"{docx_path.stem}_page_001.png", case, report)
        _write_expected_contracts(case_dir, case)
        generated.append(case_dir)
    return generated
```

Use a Chinese system font selected from `Microsoft YaHei`, `SimSun`, or `Noto Sans CJK`; fail with an actionable error when no CJK font is available. PNG pages are A4-like, high-contrast, and include the synthetic banner plus `测试专用` mark. Do not synthesize QR codes.

- [ ] **Step 5: Add content and privacy assertions**

The tests scan extracted DOCX XML and JSON for the banner, inspect generated PNG dimensions and nonblank pixels, and reject patterns matching 18-digit citizen identifiers, 11-digit mobile numbers, or reference institution names. Case text uses only catalog synthetic labels such as `测试人员甲` and `测试机构A`.

- [ ] **Step 6: Run generator tests and generate the committed corpus**

Run:

```powershell
python -m pytest tests/test_v058_case_generation.py -q
python scripts/generate_v058_cases.py --output "测试用例/v058随机条文" --overwrite
```

Expected: tests pass; ten directories and one root manifest are generated.

- [ ] **Step 7: Commit generator and corpus**

```powershell
git add pyproject.toml scripts/generate_v058_cases.py tests/test_v058_case_generation.py "测试用例/v058随机条文"
git commit -m "test: add ten synthetic v0.58 case packages"
```

### Task 3: Golden Semantic Replay Harness

**Files:**
- Create: `tests/v058_case_helpers.py`
- Create: `tests/test_v058_case_acceptance.py`
- Modify only if necessary: `tests/semantic_runtime.py`

**Interfaces:**
- Consumes: each case's `semantic_assertions.json` and `expected_outcome.json`.
- Produces: `build_semantic_workflow(case_dir: Path) -> CaseWorkflow` and `assert_expected_outcome(case_dir: Path, result: WorkflowResult) -> None`.

- [ ] **Step 1: Write failing ten-case discovery and replay tests**

```python
@pytest.mark.parametrize("case_dir", discover_v058_cases(), ids=lambda p: p.name)
def test_v058_case_matches_golden_contract(case_dir):
    workflow = build_semantic_workflow(case_dir)
    result = replay_v058_case(case_dir, workflow)
    assert_expected_outcome(case_dir, result)
```

- [ ] **Step 2: Run the acceptance test and confirm RED**

Run: `python -m pytest tests/test_v058_case_acceptance.py -q`

Expected: FAIL because helper functions are missing.

- [ ] **Step 3: Implement golden runtime construction without prose parsing**

```python
def build_semantic_workflow(case_dir: Path) -> CaseWorkflow:
    assertions = json.loads((case_dir / "expected/semantic_assertions.json").read_text(encoding="utf-8"))
    facts_by_material = defaultdict(list)
    for item in assertions["assertions"]:
        facts_by_material[item["source_material_id"]].append(item["agent_fact"])
    runtime = SemanticFixtureRuntime(dict(facts_by_material))
    workflow = CaseWorkflow.demo()
    for agent in (workflow.text_agent, workflow.pic_agent, workflow.report_image_agent):
        agent.runtime = runtime
    return workflow
```

- [ ] **Step 4: Implement explicit output assertions**

Validate required/forbidden Claim identities, support/opposition/ambiguity, assessment status, Bayesian model runs or abstention reasons, required/forbidden legal articles, ValidationIssue types, and forbidden final-conclusion phrases. Error messages must include corpus ID and expected/actual values.

- [ ] **Step 5: Run the suite and preserve each genuine generic failure**

Run: `python -m pytest tests/test_v058_case_acceptance.py -q --maxfail=10`

Expected at this stage: tests either pass or fail with precise shared-contract diagnostics; no acceptance expectation is weakened to fit current code.

- [ ] **Step 6: Commit the harness before production fixes**

```powershell
git add tests/v058_case_helpers.py tests/test_v058_case_acceptance.py tests/semantic_runtime.py
git commit -m "test: define v0.58 ten-case semantic acceptance"
```

### Task 4: Case-Neutral Semantic and Claim Corrections

**Files:**
- Modify only when implicated by failing tests: `case_agent_demo/agent_runtime.py`
- Modify only when implicated by failing tests: `case_agent_demo/agents.py`
- Modify only when implicated by failing tests: `case_agent_demo/evidence_reasoning.py`
- Modify only when implicated by failing tests: `case_agent_demo/models.py`
- Modify only when implicated by failing tests: `case_agent_demo/relation_tools.py`
- Modify only when implicated by failing tests: `config/prompts/text_agent.md`
- Modify only when implicated by failing tests: `config/prompts/report_image_agent.md`
- Modify only when implicated by failing tests: `config/prompts/image_evidence_agent.md`
- Test: `tests/test_v058_case_acceptance.py`

**Interfaces:**
- Consumes: open semantic assertions with explicit actor, target/object, event, stance, assertion role, and evidence span.
- Produces: correctly grouped supporting, opposing, and ambiguous EvidenceClaims without keyword inference.

- [ ] **Step 1: Isolate the first shared semantic/Claim failure**

Run: `python -m pytest tests/test_v058_case_acceptance.py -q -x`

Expected: one concrete mismatch whose fix applies to more than one possible case.

- [ ] **Step 2: Add the smallest regression test that names the semantic rule**

Examples of allowed generic assertions:

```python
def test_alternative_explanation_opposes_attribution_without_proving_alternative(): ...
def test_partial_admission_creates_separate_supported_and_opposed_claims(): ...
def test_result_claim_does_not_prove_actor_conduct_claim(): ...
def test_statutory_exception_fact_remains_separate_from_legal_outcome(): ...
```

- [ ] **Step 3: Run the focused test and confirm RED**

Run the exact new pytest node and confirm it fails because the shared rule is missing.

- [ ] **Step 4: Implement the minimal schema/grouping correction**

Preserve open predicates. Normalize only structural enums and explicit relationships; unresolved or malformed model outputs remain ambiguous. Do not inspect article numbers, case names, or prose keywords.

- [ ] **Step 5: Run focused and ten-case tests**

Run:

```powershell
python -m pytest <focused-test-node> -q
python -m pytest tests/test_v058_case_acceptance.py -q
```

Expected: the focused regression passes and no prior case regresses.

- [ ] **Step 6: Repeat RED-GREEN only for remaining generic failures, then commit**

```powershell
git add case_agent_demo config/prompts tests/test_v058_case_acceptance.py tests/test_*.py
git commit -m "fix: generalize semantic evidence handling for v0.58"
```

Review the staged diff before commit and unstage every unrelated user file.

### Task 5: Bayesian Selection, Abstention, and Legal Retrieval Corrections

**Files:**
- Modify only when tests prove necessity: `case_agent_demo/bayesian_tool.py`
- Modify only when tests prove necessity: `case_agent_demo/evidence_reasoning_engine.py`
- Modify only when tests prove necessity: `case_agent_demo/legal_kb.py`
- Modify only when tests prove necessity: `case_agent_demo/final_conflict_agent.py`
- Modify only when tests prove necessity: `config/bayesian_models/registry.json`
- Test: `tests/test_v058_case_acceptance.py`

**Interfaces:**
- Consumes: Claim assessments and generic registry mappings.
- Produces: audited Bayesian runs or explicit abstentions, cited law candidates, and grounded validation issues.

- [ ] **Step 1: Add focused failing tests for every shared inference defect**

Allowed patterns:

```python
def test_unmapped_claims_abstain_without_prior_fabrication(): ...
def test_actor_attribution_is_not_inferred_from_result_exists(): ...
def test_legal_candidate_does_not_change_claim_status(): ...
def test_supported_exception_fact_does_not_choose_punishment(): ...
```

- [ ] **Step 2: Confirm each test is RED before implementation**

Run each exact pytest node and record expected versus actual output in the workflow run review file.

- [ ] **Step 3: Implement only reusable relationship or gate changes**

Registry changes may introduce a generic relationship component only when at least two legal contexts can reuse it. Every component remains versioned JSON with calibration status, parameter hash, required inputs, output nodes, and abstention rules.

- [ ] **Step 4: Run inference, RAG, and ten-case suites**

Run:

```powershell
python -m pytest tests/test_bayesian_tool.py tests/test_bayesian_activation_safety.py tests/test_legal_rag_offense_precision.py tests/test_final_conflict_agent.py -q
python -m pytest tests/test_v058_case_acceptance.py -q
```

- [ ] **Step 5: Commit only verified generic changes**

```powershell
git add case_agent_demo/bayesian_tool.py case_agent_demo/evidence_reasoning_engine.py case_agent_demo/legal_kb.py case_agent_demo/final_conflict_agent.py config/bayesian_models tests
git commit -m "fix: preserve inference boundaries across v0.58 cases"
```

### Task 6: Live Agent Acceptance Runner

**Files:**
- Create: `scripts/run_v058_live_agent_acceptance.py`
- Create: `tests/test_v058_live_agent_runner.py`
- Ignore generated output: `.gitignore`

**Interfaces:**
- Consumes: generated DOCX/PNG cases and configured runtime from existing project configuration.
- Produces: `artifacts/v058-live-agent/<timestamp>/summary.json`, per-material raw JSON, parse errors, unavailable-model status, and semantic diffs.

- [ ] **Step 1: Write failing offline runner tests**

```python
def test_live_runner_reports_model_unavailable_without_keyword_fallback(tmp_path):
    report = run_live_acceptance(corpus_root=FIXTURE_ROOT, output_root=tmp_path, runtime=UnavailableRuntime())
    assert report["status"] == "model_unavailable"
    assert report["fallback_used"] is False
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `python -m pytest tests/test_v058_live_agent_runner.py -q`

- [ ] **Step 3: Implement model-aware execution and semantic diffing**

The runner calls the existing Text, ReportImage, and Image agents, stores raw model output before parsing, compares actor/target/object/predicate/stance/event/source fields to golden assertions, and never feeds golden assertions into live extraction.

- [ ] **Step 4: Run offline tests and then the configured live command**

Run:

```powershell
python -m pytest tests/test_v058_live_agent_runner.py -q
python scripts/run_v058_live_agent_acceptance.py --corpus "测试用例/v058随机条文" --output artifacts/v058-live-agent
```

Expected: either a completed integration report or explicit `model_unavailable`; no keyword fallback.

- [ ] **Step 5: Commit runner code, not generated model outputs**

```powershell
git add scripts/run_v058_live_agent_acceptance.py tests/test_v058_live_agent_runner.py .gitignore
git commit -m "test: add v0.58 live agent acceptance runner"
```

### Task 7: Full Regression and Fixture Reconciliation

**Files:**
- Modify: `tests/test_original_docx_replay.py`
- Modify only as proven necessary: other existing tests referencing deleted root fixtures.
- Update: `workflow-runs/20260714-002417-v058-cases-dify-migration/reviews.md`

**Interfaces:**
- Consumes: user-preserved reference fixtures under `测试用例/伤害/`.
- Produces: green v0.56 regression plus v0.58 acceptance without restoring deleted duplicate fixtures.

- [ ] **Step 1: Write or adjust a failing path assertion**

```python
REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "测试用例" / "伤害"
assert (REFERENCE_ROOT / "test_he.docx").is_file()
```

- [ ] **Step 2: Confirm the old path fails and the preserved path exists**

Run: `python -m pytest tests/test_original_docx_replay.py -q`

- [ ] **Step 3: Change only fixture locations, not expected semantics**

Point old root fixture references to `测试用例/伤害/`; do not recreate deleted duplicate documents.

- [ ] **Step 4: Run all project tests**

Run: `python -m pytest -q`

Expected: zero failures. Record pass count, duration, skipped tests, and warnings in `reviews.md`.

- [ ] **Step 5: Run the detachable visualization plugin tests**

Run: `python -m pytest plugins/reasoning_visualizer/tests -q`

Expected: zero failures, including EvidenceGraph, EvidenceClaim, derived Claim, Bayesian, and validation layers.

- [ ] **Step 6: Commit fixture-only reconciliation**

```powershell
git add tests/test_original_docx_replay.py workflow-runs/20260714-002417-v058-cases-dify-migration/reviews.md
git commit -m "test: reconcile preserved v0.56 reference fixtures"
```

### Task 8: v0.58 Release Documentation and Version

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `项目介绍.md`
- Modify: `技术手册.md`
- Modify: `用户手册.md`
- Create: `docs/V058_TEN_CASE_VALIDATION.md`

**Interfaces:**
- Consumes: verified run results and generated corpus.
- Produces: audience-specific v0.58 explanation while preserving accurate v0.51 and v0.56 history.

- [ ] **Step 1: Add a failing version/documentation test**

```python
def test_release_documents_declare_v058_without_erasing_v056_history():
    assert 'version = "0.58.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("README.md", "项目介绍.md", "技术手册.md", "用户手册.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "v0.56" in text
        assert "v0.58" in text
```

- [ ] **Step 2: Confirm RED at version 0.56.0**

Run: `python -m pytest tests/test_v058_release_docs.py -q`

- [ ] **Step 3: Update version and documentation by audience**

`项目介绍.md` explains the ten-case validation and safe boundaries for nontechnical leadership; `技术手册.md` explains golden semantic replay, live-Agent comparison, generic fixes, Bayesian runs/abstentions, and test evidence; `用户手册.md` explains how to run corpus replay and read outcomes; `README.md` provides the concise release map. Do not present expert-prior Bayesian values as truth probabilities.

- [ ] **Step 4: Run release docs and full tests**

Run:

```powershell
python -m pytest tests/test_v058_release_docs.py -q
python -m pytest -q
```

- [ ] **Step 5: Commit the release changes**

```powershell
git add pyproject.toml README.md "项目介绍.md" "技术手册.md" "用户手册.md" docs/V058_TEN_CASE_VALIDATION.md tests/test_v058_release_docs.py
git commit -m "docs: release case-agent demo v0.58"
```

### Task 9: Machine-Readable Acceptance Report

**Files:**
- Create: `scripts/build_v058_acceptance_report.py`
- Create: `tests/test_v058_acceptance_report.py`
- Generate: `artifacts/v058-acceptance/summary.json`
- Generate: `artifacts/v058-acceptance/summary.md`

**Interfaces:**
- Consumes: deterministic pytest/JUnit output, live-Agent summary, sampling manifest, corpus hashes, and git revision.
- Produces: stable JSON and Markdown release evidence for Dify parity comparison.

- [ ] **Step 1: Write failing report-schema tests**

```python
def test_acceptance_report_covers_all_ten_cases(tmp_path):
    report = build_report(corpus_root=CORPUS_ROOT, output_root=tmp_path)
    assert report["version"] == "0.58.0"
    assert len(report["cases"]) == 10
    assert all(item["deterministic_status"] == "passed" for item in report["cases"])
    assert report["sampling"]["seed"] == 58
```

- [ ] **Step 2: Confirm RED, implement report builder, then confirm GREEN**

Run: `python -m pytest tests/test_v058_acceptance_report.py -q`

The report includes case ID, law/article, material hashes, expected complexity, Claim statuses, Bayesian run/abstention, legal candidates, ValidationIssues, deterministic status, live status, model versions, parameter hashes, and git revision.

- [ ] **Step 3: Generate final local report and verify hashes**

Run:

```powershell
python scripts/build_v058_acceptance_report.py --corpus "测试用例/v058随机条文" --output artifacts/v058-acceptance
python -m pytest tests/test_v058_acceptance_report.py -q
```

- [ ] **Step 4: Commit report tooling and the stable summary**

```powershell
git add scripts/build_v058_acceptance_report.py tests/test_v058_acceptance_report.py artifacts/v058-acceptance/summary.json artifacts/v058-acceptance/summary.md
git commit -m "test: publish v0.58 acceptance evidence"
```

### Task 10: v0.58 Completion Gate

**Files:**
- Update: `workflow-runs/20260714-002417-v058-cases-dify-migration/status.md`
- Update: `workflow-runs/20260714-002417-v058-cases-dify-migration/reviews.md`

**Interfaces:**
- Consumes: all test and acceptance outputs.
- Produces: signed-off local v0.58 baseline for the Dify migration plan.

- [ ] **Step 1: Run fresh verification commands**

```powershell
python -m pytest -q
python -m pytest plugins/reasoning_visualizer/tests -q
python scripts/sample_v058_provisions.py --db legal_knowledge/index/legal_kb.sqlite3 --seed 58 --check "测试用例/v058随机条文/sampling_manifest.json"
python scripts/build_v058_acceptance_report.py --corpus "测试用例/v058随机条文" --output artifacts/v058-acceptance --verify
```

- [ ] **Step 2: Audit for forbidden case-specific logic**

Run a production-code scan for all corpus IDs, sampled article numbers, synthetic names, and scenario locations. Expected: no matches under `case_agent_demo/` or runtime `config/`; matches are allowed only in tests, generated corpus, and documentation.

- [ ] **Step 3: Review git diff and status**

Confirm no secrets, reference PII, generated caches, unrelated user changes, or removed prompts are included. Record exact commands and outputs in `reviews.md`.

- [ ] **Step 4: Mark only the v0.58 local baseline complete**

Update workflow status to indicate Dify migration is ready to begin. Do not mark the overall user goal complete.
