# Task 3: Authority Anchors Report

## Scope

Implemented authority-aware claim assessment without changing existing public call signatures or adding dependencies.

- Added `AuthorityAssessment` and exposed per-assertion assessments on `ClaimAssessment`.
- Added `AuthorityValidator`, which reads only explicit nested `assertion.metadata["authority"]` values.
- Added JSON rules for a verified forensic injury-grade report: mean `0.99`, strength `50.0`, and mandatory human verification.
- Converted valid authority conclusions into evidence amounts. They do not assign a claim truth value.
- Restricted the authority rule to `injury_exists` and `injury_grade`; a valid forensic injury assertion has no authority effect on violence, actor identity, intent, causation, or criminal liability.
- Preserved ordinary subjective evidence for unverified or out-of-scope assertions. An ordinary denial adds normal opposing evidence, while a verified authoritative defeater sets `authority_contested`.

## RED Evidence

Command:

```powershell
python -m unittest discover -s tests -p test_authority_reasoning.py -v
```

Before implementation, the focused suite failed with the expected missing-feature error:

```text
ImportError: cannot import name 'AuthorityValidator' from 'case_agent_demo.evidence_reasoning'
```

The failing test module covered scope-limited injury-grade anchoring, resistance to an ordinary denial, authoritative reappraisal conflict, and rejection of official-sounding but unverified metadata.

## GREEN Evidence

The same focused command passed after implementation:

```text
Ran 4 tests in 0.013s
OK
```

Compatibility and final verification:

```text
python -m unittest discover -s tests -p test_evidence_reasoning_models.py -v
Ran 5 tests in 0.001s
OK

python -m unittest discover -s tests -p test_subjective_evidence.py -v
Ran 10 tests in 0.006s
OK

python -m unittest discover -s tests -v
Ran 107 tests in 0.515s
OK

python -m compileall -q case_agent_demo tests
Exit code: 0

git diff --check
Exit code: 0
```

## Review

The scoped diff contains only the requested Task 3 implementation files and this report. The validator does not inspect `source_party`, source type, or document naming to grant authority. The configuration is deliberately exact: upstream producers must supply the configured issuer, document type, every verification flag, and `human_verified: true` before an assertion can become an anchor.

## Remaining Concerns

The configured numeric amounts are evidence-support inputs, not calibrated probabilities of truth. New authority document formats or issuers require an explicit configuration update and tests; they intentionally remain unverified until then.
