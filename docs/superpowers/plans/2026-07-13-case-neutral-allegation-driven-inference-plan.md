# v0.56 案件中立证据推理实施计划

> 对应设计：`docs/superpowers/specs/2026-07-13-case-neutral-allegation-driven-inference-design.md`

## 任务 1：先建立失败测试

文件：

- `tests/test_case_neutral_workflow.py`
- `tests/test_evidence_book.py`
- `tests/test_bayesian_activation_safety.py`
- `tests/test_legal_procedure_rag.py`

覆盖：无案件类型运行、未特化事实证据册、指控/辩解/客观观察分流、全模糊与纯否认不形成正向软证据、缺失必需输入 abstain、刑诉法分类与证据审查召回。

## 任务 2：扩展案件中立领域模型

文件：

- `case_agent_demo/models.py`
- `case_agent_demo/evidence_reasoning.py`

新增 `CaseTypeContext`、`ParticipantRecord`、`AllegationRecord`、`EvidenceFinding`、`LegalCandidate`、`EvidenceBook`；为 Assertion 增加角色、时间、地点和证据类别。保留旧字段兼容。

## 任务 3：实现证据册和自动领域发现

文件：

- `case_agent_demo/evidence_book.py`
- `case_agent_demo/domain_affinity.py`
- `case_agent_demo/evidence_reasoning_engine.py`

由 Assertion、ClaimAssessment 和图确定性构建证据册。案件域以 Claim/材料为主，人工类型仅作为可选提示。

## 任务 4：解除人工案件类型门禁

文件：

- `case_agent_demo/workflow.py`
- `case_agent_demo/cli.py`
- `case_agent_demo/agents.py`
- `case_agent_demo/case_replay.py`

`CaseWorkflow.run()` 默认自动执行；保留兼容严格模式。Reasoning 报告不再无条件宣称“人工确认”。WorkflowResult 返回案件类型上下文和证据册。

## 任务 5：修复贝叶斯激活和 abstain

文件：

- `case_agent_demo/bayesian_tool.py`
- `config/bayesian_models/registry.json`

只有明确指控激活候选组件；域标签不能单独激活；纯否认、全模糊或完全未知评估不进入正向软证据；必需输入不足时返回可审计 abstain，不运行先验补值。

## 任务 6：扩展可复用事实谓词，不按罪名特化

文件：

- `case_agent_demo/models.py`
- `config/bayesian_models/registry.json`
- 必要时新增少量关系组件 JSON

优先增加跨案件复用的 `deception_statement`、`mistaken_belief`、`voluntary_disposition`、`property_loss` 等事实谓词和 `deception_disposition` 关系组件，不新增“诈骗案件模块”。其他未知谓词继续走安全兜底。

## 任务 7：RAG 目的分离和刑诉法分类

文件：

- `case_agent_demo/legal_kb.py`
- `case_agent_demo/tools.py`

修正《刑事诉讼法》的标题和 `criminal_procedure_law` 类型；实现 `allegation_discovery`、`legal_basis`、`evidence_review` 的输入和排序差异；重新索引法律库并验证清单。

## 任务 8：更新回放、报告和文档

文件：

- `tests/test_case_replay_corpus.py`
- `测试用例/` 新增未特化案件回放
- `README.md`
- `项目介绍.md`
- `技术手册.md`
- `用户手册.md`

现有手册只在末尾追加 v0.56 章节，不修改 v0.51 或用户已有内容。五类样例改称回归覆盖，不再称支持范围。

## 任务 9：验证和完成度审计

运行：

```powershell
python -m pytest
python -m case_agent_demo.legal_kb_cli --root legal_knowledge search "证据必须经过查证属实 非法证据排除 排除合理怀疑" --top-k 8
python -m case_agent_demo.cli --sample
```

逐项核对设计文档第 11 节验收条件，并记录测试数、RAG 清单、未知案件回放和输出措辞。
