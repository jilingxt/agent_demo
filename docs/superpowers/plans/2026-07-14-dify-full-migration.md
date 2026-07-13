# Dify Full Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the verified v0.58 evidence workflow as a Dify 1.15.0 Tool Plugin plus importable DSL 0.6.0 workflow, run it locally, verify ten-case parity, and produce an independent secret-free delivery folder.

**Architecture:** Dify owns file input, extraction/vision/LLM orchestration, report generation, execution trace, and user-facing outputs. A Python 3.12 Tool Plugin bundles the existing deterministic evidence, Bayesian, legal RAG, validation, and visualization runtime behind four structured tools; it is not a second hand-written inference implementation.

**Tech Stack:** Dify 1.15.0, Workflow DSL 0.6.0, Python 3.12 Tool Plugin, Docker Compose, existing SQLite/FTS5/dense-vector legal index, pytest, PowerShell, SHA-256 checksums.

## Global Constraints

- Primary migration path: `F:\dify\case-evidence-v058`.
- Independent delivery path: `F:\汇报\Va1ha11a_dify_v0.58`.
- Expose exactly four tools: `evaluate_evidence`, `retrieve_legal_basis`, `final_validate`, `render_reasoning_snapshot`.
- Bundle current runtime modules and configuration; do not fork inference algorithms into Dify wrappers.
- Keep the SQLite legal index as the parity-authoritative retriever; include the three PDFs only for optional Dify Knowledge inspection.
- Never include `F:\dify\docker\.env`, credentials, API keys, tokens, caches, model downloads, or real case outputs in source or delivery artifacts.
- Put new Docker/WSL data on `E:` if relocation is needed; never delete or move existing Docker data without resolving and verifying absolute paths.
- Do not declare migration complete until the plugin is installed, DSL imports, one synthetic end-to-end case succeeds, all ten parity checks run, and the delivery folder passes secret and checksum verification.

---

## File Map

- `F:\dify\case-evidence-v058\plugin\manifest.yaml`: Dify plugin manifest.
- `...\plugin\main.py`: plugin entry point.
- `...\plugin\provider\case_evidence.yaml` and `.py`: provider declaration and implementation.
- `...\plugin\tools\*.yaml` and `.py`: four tool schemas and adapters.
- `...\plugin\case_agent_demo\`: copied verified runtime package.
- `...\plugin\config\`: copied prompt, Bayesian, authority, and legal-element configuration.
- `...\plugin\legal_knowledge\index\legal_kb.sqlite3`: read-only legal index.
- `...\app\case-evidence-v058.yml`: importable Dify Workflow DSL 0.6.0.
- `...\tests\`: plugin parity, schema, DSL, package, and secret tests.
- `...\scripts\sync-runtime.ps1`: allowlisted runtime copy.
- `...\scripts\package-plugin.ps1`: deterministic package builder.
- `...\scripts\install-local.ps1`: local install/import helper with no embedded credentials.
- `...\scripts\smoke-test.ps1`: end-to-end synthetic run.
- `...\scripts\build-delivery.ps1`: standalone delivery and checksums.

### Task 1: Migration Workspace and Runtime Sync

**Files:**
- Create: `F:\dify\case-evidence-v058\scripts\sync-runtime.ps1`
- Create: `F:\dify\case-evidence-v058\tests\test_runtime_sync.py`
- Create: `F:\dify\case-evidence-v058\MIGRATION.md`
- Create: `F:\dify\case-evidence-v058\CAPABILITY_MAPPING.md`

**Interfaces:**
- Consumes: verified `F:\汇报\Va1ha11a_demo` v0.58 source tree.
- Produces: allowlisted plugin runtime tree with recorded source revision and hashes.

- [ ] **Step 1: Write failing allowlist tests**

```python
def test_synced_runtime_contains_only_required_assets():
    assert (PLUGIN / "case_agent_demo/evidence_reasoning_engine.py").is_file()
    assert (PLUGIN / "legal_knowledge/index/legal_kb.sqlite3").is_file()
    assert not (PLUGIN / "config/api_keys.toml").exists()
    assert not (PLUGIN / "tests").exists()
    assert not list(PLUGIN.rglob("__pycache__"))
```

- [ ] **Step 2: Confirm RED**

Run from `F:\dify\case-evidence-v058`: `python -m pytest tests/test_runtime_sync.py -q`

- [ ] **Step 3: Implement explicit sync allowlists**

`sync-runtime.ps1` removes and recreates only the migration build directories, verifies every resolved destination remains under `F:\dify\case-evidence-v058\plugin`, copies `case_agent_demo/*.py`, selected `config/prompts`, `config/bayesian_models`, `config/authority_rules.json`, `config/legal_elements`, the SQLite index, and writes `runtime-manifest.json` with source git revision and SHA-256 values.

- [ ] **Step 4: Run sync and tests**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-runtime.ps1 -SourceRoot "F:\汇报\Va1ha11a_demo"
python -m pytest tests/test_runtime_sync.py -q
```

- [ ] **Step 5: Document one-to-one capability ownership**

`CAPABILITY_MAPPING.md` maps every current workflow stage to a Dify node or one of the four plugin tools and explicitly identifies no duplicate inference implementation.

### Task 2: Plugin Manifest, Provider, and Tool Schemas

**Files:**
- Create: `plugin/manifest.yaml`
- Create: `plugin/main.py`
- Create: `plugin/provider/case_evidence.yaml`
- Create: `plugin/provider/case_evidence.py`
- Create: `plugin/tools/evaluate_evidence.yaml`
- Create: `plugin/tools/retrieve_legal_basis.yaml`
- Create: `plugin/tools/final_validate.yaml`
- Create: `plugin/tools/render_reasoning_snapshot.yaml`
- Create: `tests/test_plugin_schema.py`

**Interfaces:**
- Produces four named tools with JSON-string inputs/outputs that remain within Dify schema nesting limits.

- [ ] **Step 1: Write failing manifest/schema tests**

```python
def test_manifest_declares_exact_tool_set():
    manifest = load_yaml(PLUGIN / "manifest.yaml")
    assert manifest["type"] == "plugin"
    assert manifest["version"] == "0.58.0"
    assert discover_tool_names(PLUGIN / "tools") == {"evaluate_evidence", "retrieve_legal_basis", "final_validate", "render_reasoning_snapshot"}
```

- [ ] **Step 2: Confirm RED**

Run: `python -m pytest tests/test_plugin_schema.py -q`

- [ ] **Step 3: Implement Dify 1.15.0-compatible manifest and schemas**

Each tool takes a required JSON string plus optional purpose/model version fields. Outputs are named JSON strings and, for visualization, an HTML blob/file. The provider has no credential fields because model credentials remain in Dify model providers.

- [ ] **Step 4: Validate schemas against local Dify plugin examples**

Run local schema tests and compare keys with `F:\dify\api` plugin entities. Expected: no unknown manifest/tool schema fields.

### Task 3: Four Thin Tool Adapters

**Files:**
- Create: `plugin/tools/common.py`
- Create: `plugin/tools/evaluate_evidence.py`
- Create: `plugin/tools/retrieve_legal_basis.py`
- Create: `plugin/tools/final_validate.py`
- Create: `plugin/tools/render_reasoning_snapshot.py`
- Create: `tests/test_tool_parity.py`

**Interfaces:**
- `evaluate_evidence(payload_json: str) -> dict[str, object]`
- `retrieve_legal_basis(payload_json: str) -> dict[str, object]`
- `final_validate(payload_json: str) -> dict[str, object]`
- `render_reasoning_snapshot(payload_json: str) -> dict[str, object]`

- [ ] **Step 1: Write failing parity tests using a generated v0.58 case**

```python
def test_evaluate_tool_matches_local_engine():
    payload = load_tool_payload(CORPUS / "PS-51_完整承认")
    expected = evaluate_locally(payload)
    actual = invoke_tool("evaluate_evidence", payload)
    assert canonical_reasoning_projection(actual) == canonical_reasoning_projection(expected)
```

- [ ] **Step 2: Confirm RED**

Run: `python -m pytest tests/test_tool_parity.py -q`

- [ ] **Step 3: Implement JSON validation and dataclass adapters**

`common.py` parses UTF-8 JSON, rejects missing required fields and unregistered model versions, converts current dataclasses with `dataclasses.asdict`, canonicalizes sets/paths, and returns structured errors without logging evidence text or secrets.

- [ ] **Step 4: Delegate to current engines**

`evaluate_evidence` calls `EvidenceReasoningEngine`; `retrieve_legal_basis` opens bundled `legal_kb.sqlite3` read-only and calls current retrieval; `final_validate` calls `FinalConflictAgent`; `render_reasoning_snapshot` calls the detachable visualizer renderer copied as a runtime dependency. No calculation is duplicated in wrappers.

- [ ] **Step 5: Run all four parity tests**

Run: `python -m pytest tests/test_tool_parity.py -q`

Expected: canonical structured outputs match local v0.58 for all ten corpus cases.

### Task 4: Importable Workflow DSL 0.6.0

**Files:**
- Create: `app/case-evidence-v058.yml`
- Create: `tests/test_dsl.py`

**Interfaces:**
- Consumes: uploaded files, optional case-type hint, authority-verification JSON, and registered model-version override.
- Produces: report, EvidenceBook JSON, validation JSON, audit JSON, and visualization HTML/file.

- [ ] **Step 1: Write failing DSL graph tests**

```python
def test_dsl_has_required_nodes_and_resolved_edges():
    graph = load_dsl(APP / "case-evidence-v058.yml")
    assert graph["version"] == "0.6.0"
    assert required_node_titles(graph) >= {"开始", "文档提取", "文本语义抽取", "图片语义抽取", "证据评估", "法律检索", "报告初稿", "最终校验", "报告修订", "结束"}
    assert unresolved_variable_selectors(graph) == []
```

- [ ] **Step 2: Confirm RED**

Run: `python -m pytest tests/test_dsl.py -q`

- [ ] **Step 3: Build the complete DSL from local Dify 1.15.0 examples**

The workflow branches documents and images, uses the existing three semantic prompts verbatim in corresponding LLM nodes, aggregates source-preserving JSON, invokes the four tools, generates a Claim-centered report, validates, revises, and returns all required outputs. Model-provider selectors are declared as operator-configured workflow environment variables and never contain credentials.

- [ ] **Step 4: Run static DSL validation**

Run: `python -m pytest tests/test_dsl.py -q`

Expected: all node IDs, edge endpoints, variable selectors, tool names, output variables, and DSL version validate.

### Task 5: Deterministic Plugin Packaging

**Files:**
- Create: `scripts/package-plugin.ps1`
- Create: `tests/test_plugin_package.py`
- Generate: `dist/case_evidence_v058.difypkg`
- Generate: `dist/SHA256SUMS.txt`

**Interfaces:**
- Consumes: synced plugin tree.
- Produces: installable plugin package and hashes without secrets/caches.

- [ ] **Step 1: Write failing package-content tests**

```python
def test_package_has_manifest_and_no_secrets():
    names = package_names(DIST / "case_evidence_v058.difypkg")
    assert "manifest.yaml" in names
    assert all("api_keys" not in name and ".env" not in name for name in names)
```

- [ ] **Step 2: Confirm RED, then implement packaging**

The script invokes the official Dify plugin pack command when available; otherwise it uses the exact archive layout accepted by local Dify 1.15.0 after validating manifest and tool schemas. It normalizes timestamps/order for repeatable hashes.

- [ ] **Step 3: Build twice and compare hashes**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-plugin.ps1
Copy-Item dist/case_evidence_v058.difypkg dist/first.difypkg
powershell -ExecutionPolicy Bypass -File scripts/package-plugin.ps1
Get-FileHash dist/first.difypkg,dist/case_evidence_v058.difypkg -Algorithm SHA256
```

Expected: identical hashes.

### Task 6: Safe Local Dify Startup, Plugin Install, and DSL Import

**Files:**
- Create: `scripts/check-docker-storage.ps1`
- Create: `scripts/install-local.ps1`
- Create: `VERIFICATION.md`

**Interfaces:**
- Consumes: existing `F:\dify\docker` installation, plugin package, DSL, operator-supplied local session/config.
- Produces: running Dify 1.15.0 with installed plugin and imported workflow.

- [ ] **Step 1: Implement read-only storage preflight**

The script reports Docker Desktop state, WSL distributions, Docker data-root, resolved VHDX paths, and C/F/E free space. It refuses startup if new image data would land on C or F below a conservative free-space floor. It does not move or delete data.

- [ ] **Step 2: Run preflight and record results**

Run: `powershell -ExecutionPolicy Bypass -File scripts/check-docker-storage.ps1 -RequireDrive E`

If storage relocation is required, use Docker Desktop-supported configuration to create/use an E:-based data location, then re-run preflight. Never print `.env` contents.

- [ ] **Step 3: Start Dify and verify service health**

Run from `F:\dify\docker`:

```powershell
docker compose up -d
docker compose ps
```

Expected: required Dify services are healthy or running; failures are captured in `VERIFICATION.md` without secrets.

- [ ] **Step 4: Install plugin and import DSL**

`install-local.ps1` uses the local Dify API/CLI supported by 1.15.0, reads operator tokens only from process environment, installs `dist/case_evidence_v058.difypkg`, imports `app/case-evidence-v058.yml`, and records returned non-secret plugin/app IDs in a local verification JSON excluded from delivery.

- [ ] **Step 5: Verify installed objects**

Query local Dify APIs or UI state to confirm exact plugin version `0.58.0`, all four tools, and one imported workflow with no unresolved dependencies.

### Task 7: End-to-End Smoke and Ten-Case Parity

**Files:**
- Create: `scripts/smoke-test.ps1`
- Create: `tests/test_dify_parity_report.py`
- Generate: `verification/dify-ten-case-parity.json`
- Generate: `verification/dify-ten-case-parity.md`

**Interfaces:**
- Consumes: installed Dify workflow and ten synthetic cases.
- Produces: comparable local-vs-Dify projections and end-to-end artifacts.

- [ ] **Step 1: Write failing parity report tests**

```python
def test_parity_report_covers_ten_cases_and_all_contract_fields():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert len(report["cases"]) == 10
    assert all(item["claims_match"] for item in report["cases"])
    assert all(item["bayesian_or_abstention_match"] for item in report["cases"])
    assert all(item["legal_candidates_match"] for item in report["cases"])
    assert all(item["validation_issues_match"] for item in report["cases"])
```

- [ ] **Step 2: Run one smoke case through Dify**

Use the full-admission synthetic public-security case. Confirm file input, semantic extraction, plugin evaluation, legal retrieval, report generation, final validation, and visualization output all execute.

- [ ] **Step 3: Run all ten cases and canonicalize outputs**

The script uploads each package's required materials, polls the workflow run, stores only synthetic outputs, and compares Claim identities/statuses, Bayesian run/abstention, cited legal articles/chunks, ValidationIssue types, and forbidden final conclusions with local v0.58 acceptance results.

- [ ] **Step 4: Run parity tests**

Run: `python -m pytest tests/test_dify_parity_report.py -q`

Expected: all ten parity projections pass. Model-specific wording differences are recorded but do not replace structural checks.

### Task 8: Standalone Delivery Folder

**Files:**
- Create: `scripts/build-delivery.ps1`
- Create: `tests/test_delivery.py`
- Create: `DELIVERY_README.md`
- Generate: `F:\汇报\Va1ha11a_dify_v0.58\`

**Interfaces:**
- Consumes: verified DSL, plugin package/source, law assets, corpus, configuration templates, and verification reports.
- Produces: independently installable secret-free delivery with checksums.

- [ ] **Step 1: Write failing delivery-contract tests**

```python
def test_delivery_is_complete_and_secret_free():
    assert (DELIVERY / "app/case-evidence-v058.yml").is_file()
    assert (DELIVERY / "plugin/case_evidence_v058.difypkg").is_file()
    assert len(list((DELIVERY / "test-corpus").glob("CR-*"))) == 5
    assert len(list((DELIVERY / "test-corpus").glob("PS-*"))) == 5
    assert verify_sha256s(DELIVERY / "SHA256SUMS.txt") == []
    assert secret_scan(DELIVERY) == []
```

- [ ] **Step 2: Confirm RED, then implement safe delivery build**

The script resolves the destination, verifies it is exactly beneath `F:\汇报` and named `Va1ha11a_dify_v0.58`, removes only a prior generated delivery after path verification, copies allowlisted artifacts, writes install instructions and checksums, and excludes `.env`, keys, tokens, caches, local IDs, model downloads, and real outputs.

- [ ] **Step 3: Build and verify delivery**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-delivery.ps1 -Destination "F:\汇报\Va1ha11a_dify_v0.58"
python -m pytest tests/test_delivery.py -q
```

- [ ] **Step 4: Fresh final verification**

Run plugin schema tests, tool parity tests, DSL tests, package tests, local Dify smoke/parity tests, delivery tests, checksum verification, and secret scan in one fresh command sequence. Record exact outputs in `VERIFICATION.md` and the workspace workflow review file.

- [ ] **Step 5: Complete only after every gate is evidenced**

Confirm installed plugin, imported DSL, successful smoke run, ten-case parity, independent delivery, valid checksums, and zero secret findings. Only then mark the overall goal complete.
