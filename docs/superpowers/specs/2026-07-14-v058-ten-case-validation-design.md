# v0.58 Ten-Case Validation Design

## 1. Objective

Build a reproducible, anonymized ten-case corpus from five Criminal Law provisions and five Public Security Administration Punishments Law provisions. The corpus must test admissions, denials, partial admissions, alternative explanations, evidence insufficiency, non-offense disputes, statutory exceptions, and the boundary between fact support and legal conclusions. Failures must drive case-neutral improvements rather than article-specific Python branches.

## 2. Sampling Contract

The source of truth is `legal_knowledge/index/legal_kb.sqlite3`, which was built from `law_DB/刑法.pdf` and `law_DB/治安管理处罚法.pdf`.

- Random seed: `58`.
- Criminal Law pool: chunks whose metadata part is `第二编 分则`.
- Public Security Administration pool: chunks whose metadata chapter is `第三章 违反治安管理的行为和处罚`.
- Each law is sampled independently so one corpus does not alter the other corpus's sequence.
- A sampled provision is rejected only when it contains no independently testable prohibited conduct, such as a pure sentencing rule. Every rejection and replacement is recorded in `sampling_manifest.json`.
- Criminal Law Article 383 is rejected because it is a punishment rule for the Article 382 offense rather than a standalone conduct definition. The next sampled substantive provision, Article 186, replaces it.

Final sample:

| Corpus ID | Law | Provision | Core factual question |
| --- | --- | --- | --- |
| `CR-353` | Criminal Law | Article 353 | Whether a person induced, deceived, instructed, or forced another person to consume drugs |
| `CR-185` | Criminal Law | Article 185 | Whether a financial institution worker used a position to divert institutional or client funds without authority |
| `CR-189` | Criminal Law | Article 189 | Whether a financial institution worker improperly accepted, paid, or guaranteed a bill and whether material loss resulted |
| `CR-429` | Criminal Law | Article 429 | Whether the setting was a battlefield, a valid rescue request existed, rescue was possible, and non-rescue caused major loss |
| `CR-186` | Criminal Law | Article 186 | Whether a regulated loan decision violated rules and involved a related party, a large amount, or major loss |
| `PS-51` | Public Security Administration Punishments Law | Article 51 | Whether the alleged actor assaulted or intentionally injured another person |
| `PS-52` | Public Security Administration Punishments Law | Article 52 | Whether alleged indecent conduct or deliberate public exposure occurred, with identity and context correctly attributed |
| `PS-31` | Public Security Administration Punishments Law | Article 31 | Whether a specific organized, coercive, deceptive, disruptive, or harmful activity occurred, rather than merely a lawful belief or private gathering |
| `PS-50` | Public Security Administration Punishments Law | Article 50 | Whether threats, insults, false accusations, harassment, tracking, or privacy dissemination occurred and can be attributed to the alleged actor |
| `PS-83` | Public Security Administration Punishments Law | Article 83 | Whether prohibited plants or materials existed and whether the statutory voluntary-removal exception applies |

## 3. Scenario Matrix

| Corpus ID | Complexity type | Required conclusion boundary |
| --- | --- | --- |
| `CR-353` | Direct denial plus conflicting statements and electronic records | Consumption may be established while inducement and actor attribution remain contested |
| `CR-185` | Business authorization or loan explanation | Fund movement is not automatically unlawful diversion; authorization and duty scope require separate findings |
| `CR-189` | Evidence insufficiency | Bill handling may be established while rule violation, responsibility, causation, and major loss remain insufficient |
| `CR-429` | Non-offense legal context | Training or exercise conditions are not automatically a battlefield; inability to rescue is not ability plus refusal |
| `CR-186` | Partial admission and regulated-decision dispute | Approval conduct may be admitted while related-party status, regulatory breach, amount, and loss remain separately assessed |
| `PS-51` | Full admission with independent corroboration | Conduct can be strongly supported, but legal classification and punishment remain human decisions |
| `PS-52` | Direct denial and alternative medical explanation | Ambiguous imagery or witness impressions must not become a supported indecent-conduct finding |
| `PS-31` | Ordinary civil or community activity dispute | Lawful gathering or expression is not converted into an offense without the provision's specific conduct and consequence facts |
| `PS-50` | Account-attribution dispute | Message content and sender identity are separate Claims; an account identifier alone does not prove the actor |
| `PS-83` | Full factual admission plus statutory exception | Cultivation facts and voluntary removal are both retained; Bayesian output must not decide punishment |

The corpus contains at least two full admissions, two direct denials, two partial admissions or alternative explanations, two evidence-insufficient cases, and two cases where the supported facts do not establish an offense.

## 4. Material Package Contract

Each case lives under `测试用例/v058随机条文/<corpus_id>_<short_name>/` and contains:

```text
case.json
sampling.json
statements/
  报案人或相关人员笔录.docx
  被指认人或行为人笔录.docx
  证人笔录.docx                  # when the scenario has a witness
reports/
  研判报告.docx
  资金流水报告.docx              # financial cases
  票据或贷款核查报告.docx         # regulated-finance cases
  电子数据核查报告.docx           # communication cases
  现场检查或专业检验报告.docx     # physical-evidence cases
report_images/
  page_001.png
  page_002.png                   # rendered synthetic report pages where useful
expected/
  semantic_assertions.json
  expected_outcome.json
```

All documents carry the visible header `合成测试材料，仅用于系统验证，不对应真实人员、单位或案件`. Names, institutions, account numbers, phone numbers, identifiers, and locations are synthetic placeholders. No reference-file personal data is copied.

Statement documents follow the question-and-answer structure of `测试用例/伤害/*.docx`, but omit unnecessary identity numbers and addresses. Report images reproduce the layout idea of `测试用例/伤害/baogao/` while using generated text, generated seals marked `测试专用`, and no real QR codes or institutions.

## 5. Semantic and Evidence Contracts

Every expected Assertion records:

- declarant and declarant role;
- actor and target or object;
- an open snake_case predicate;
- event ID and source group;
- stance: `affirm`, `deny`, or `ambiguous`;
- assertion role;
- evidence span;
- source material ID;
- whether it is an allegation, defense response, independent statement, objective report, or contextual fact.

The runtime must distinguish:

- direct denial from lack of memory;
- partial admission from total denial;
- alternative explanation from proof of the alternative;
- conduct from actor attribution;
- conduct from result;
- result from causation;
- a supported factual exception from a final legal decision.

No keyword-based case-fact fallback is restored. If semantic extraction cannot support the required fields, the material becomes `unresolved_observation / ambiguous` and the acceptance result fails visibly.

## 6. Acceptance Layers

### 6.1 Deterministic downstream tests

`SemanticFixtureRuntime` returns the golden structured outputs for the generated materials. These tests verify Claim grouping, source dependency, subjective evidence, authority scope, Bayesian selection or abstention, RAG candidates, EvidenceBook, final validation, and report boundaries.

### 6.2 Live Agent acceptance

A dedicated command runs the configured DeepSeek and Qwen runtimes against the generated DOCX and image materials, saves raw model output, and compares required semantic fields with the golden contract. This is an integration check, not a deterministic unit-test gate. Model unavailability is reported separately and never replaced with keyword guesses.

### 6.3 Outcome assertions

Each case declares:

- required and forbidden Claims;
- required support, opposition, ambiguity, or authority states;
- expected Bayesian models or explicit safe-abstention reasons;
- required and forbidden legal candidates;
- required ValidationIssue categories;
- forbidden final conclusions such as automatic guilt, offense establishment, or punishment.

## 7. v0.58 Improvement Rule

When a case fails, fixes are allowed only at shared boundaries:

- prompt schema or semantic output validation;
- generic predicate alias or relation contract;
- Claim identity and event/actor/target grouping;
- source dependency or stance handling;
- reusable Bayesian relationship component;
- legal query construction, retrieval gates, or legal-element presentation;
- final report and validation boundaries.

Forbidden fixes:

- branching on corpus ID, article number, crime name, person name, location, or a case-specific phrase;
- restoring enumerated denial, injury, property, or offense keyword inference for case facts;
- treating a legal candidate as a factual or final legal conclusion;
- forcing every case into a Bayesian component when safe abstention is correct.

The release version becomes `0.58.0` only after the ten-case acceptance suite and existing regression suite are reconciled.

## 8. Deliverables

- Ten complete synthetic case packages.
- Reproducible sampling manifest and sampling script.
- Golden semantic and outcome contracts.
- Deterministic acceptance tests and live-Agent runner.
- Case-neutral implementation fixes discovered by the corpus.
- v0.58 release documentation and version update.
- Machine-readable run report covering all ten cases.

## 9. Verification Gates

1. Sampling script reproduces the same ten provisions and records Article 383 rejection.
2. Every package contains the required materials and synthetic-data banner.
3. Every report image is readable and matches its source document.
4. Each case exercises its assigned complexity type.
5. Deterministic semantic replay passes all ten cases.
6. Live Agent acceptance is run when model configuration is available and records all deviations.
7. No case-specific fixed judgment logic appears in production code.
8. Existing v0.56 regression tests remain green after obsolete fixture paths are corrected to the user-preserved `测试用例/伤害/` location.

