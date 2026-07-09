# Case Agent Demo

一个用于案件笔录、图片证据、报告材料和法律知识库协同分析的多 Agent demo。当前版本为 `v0.51.0`。

## 核心能力

- 读取 `evidence_vault` 中的笔录、证据图片、报告图片；
- 使用 Qwen Vision 描述图片证据并识别图片文字；
- 使用 DeepSeek 文本模型 profile 区分高/低推理任务；
- `TextAgent` 按单份笔录独立提取结构化事实，不把原始笔录全文写入 Case Graph；
- `PicAgent` / `ReportImageAgent` 对图片和报告材料先提炼证据事实，再入图；
- 构建兼容旧接口的 EvidenceGraph，包含 facts、nodes、edges、claims；
- 使用 ConfidenceEngine 为 EvidenceClaim 计算可解释综合置信度；
- `ConflictAgent` 独立检测笔录、图片、报告之间的矛盾；
- 使用 LegalKnowledgeBaseTool 支持 txt/md/jsonl 入库、切片、软删除、更新和关键词检索；
- 使用 Domain Affinity 对法律知识和案件事实进行领域相关度排序；
- FinalConflictAgent 输出证据冲突、证据不足、法律依据缺失、报告越界、低置信图片等审查问题；
- Judge Agent 负责反方 challenge；
- Review Agent 负责边界复核。

## 快速运行

```powershell
cd F:\汇报\Va1ha11a_demo
pip install -e .
python -m unittest discover -s tests -v
python -m case_agent_demo.cli --sample
```

## 配置真实模型

```powershell
Copy-Item config/api_keys.example.toml config/api_keys.toml
```

填写 `config/api_keys.toml` 后运行：

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "故意伤害类案件"
```

## Prompt

Prompt 位于：

```text
config/prompts/
```

修改 prompt 后重新运行即可。

## 主要文档

- [环境配置](ENVIRONMENT.md)
- [项目介绍](项目介绍.md)
- [用户手册](用户手册.md)
- [技术手册](技术手册.md)
- [流程说明](WORKFLOW.md)

## 研判报告格式

报告类材料放入 `evidence_vault/report_images/`。该目录支持图片、Word 和 PDF：图片默认调用 Qwen 视觉模型，`.docx` 直接读取文本，`.pdf` 优先读取文本层；扫描版 PDF 请在 `evidence_vault/extracted/` 放入同名 `.txt`。

## 当前法律库匹配规则

`LegalRetrievalTool` 仍保留旧接口，并优先调用 `LegalKnowledgeBaseTool`；如果本地法律知识库没有内容，则回退到 `legal_library/laws.jsonl`。同类案件法条可按案件类型和关键词命中；跨类型法条需要更强行为要素。
