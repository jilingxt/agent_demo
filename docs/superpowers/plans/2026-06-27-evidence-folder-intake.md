# Evidence Folder Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `evidence_vault` folder and intake loader so AI analysis materials are derived from collected evidence files.

**Architecture:** Create a focused `evidence_intake.py` module that owns directory creation, file scanning, best-effort text extraction, image placeholder handling, extracted text overrides, and manifest writing. Keep `CaseWorkflow` unchanged by converting files into existing `Material` objects.

**Tech Stack:** Python standard library, `unittest`, existing `Material` and `MaterialType` models, optional PDF extraction through installed `pypdf` or `PyPDF2` only when available.

---

### Task 1: Test Evidence Vault Intake

**Files:**
- Create: `F:\汇报\agent_demo\tests\test_evidence_intake.py`

- [ ] Add tests that create a temporary evidence vault with `statements`, `report_images`, `identification_images`, and `extracted`.
- [ ] Add a `.txt` statement and assert it becomes `MaterialType.STATEMENT`.
- [ ] Add image files and extracted text overrides, asserting report images become `REPORT_IMAGE` and identification images become `EVIDENCE_IMAGE`.
- [ ] Assert `manifest.json` records source path, material id, material type, extraction status, and whether image description is required.
- [ ] Run `python -m unittest tests.test_evidence_intake -v` and verify it fails before implementation.

### Task 2: Implement Evidence Intake

**Files:**
- Create: `F:\汇报\agent_demo\case_agent_demo\evidence_intake.py`
- Create folders under `F:\汇报\agent_demo\evidence_vault`

- [ ] Implement `ensure_evidence_vault(root)`.
- [ ] Implement `EvidenceIntake.load_materials()`.
- [ ] Implement `.txt` reading, `.docx` extraction via zip/xml, optional `.pdf` extraction, and image placeholder/extracted override behavior.
- [ ] Implement `write_manifest()`.
- [ ] Run `python -m unittest tests.test_evidence_intake -v` and verify it passes.

### Task 3: Wire CLI And Docs

**Files:**
- Modify: `F:\汇报\agent_demo\case_agent_demo\cli.py`
- Modify: `F:\汇报\agent_demo\README.md`
- Modify: `F:\汇报\agent_demo\USER_GUIDE.md`

- [ ] Add `--evidence-dir` to CLI.
- [ ] Add `--init-evidence-vault` to CLI.
- [ ] Document where to place Word/PDF statements, report images, identification images, and extracted Qwen results.
- [ ] Run full tests and CLI smoke checks.
