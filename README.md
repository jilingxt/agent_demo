# Case Agent Demo

一个用于案件笔录、图片证据、报告材料和静态法律库协同分析的多 Agent demo。

## 核心能力

- 读取 `evidence_vault` 中的笔录、证据图片、报告图片；
- 使用 Qwen Vision 描述图片证据并识别图片文字；
- 使用 DeepSeek 文本模型 profile 区分高/低推理任务；
- `TextAgent` 按单份笔录独立提取结构化事实，不把原始笔录全文写入 Case Graph；
- `PicAgent` / `ReportImageAgent` 对图片和报告材料先提炼证据事实，再入图；
- 构建 Case Graph；
- `ConflictAgent` 独立检测笔录、图片、报告之间的矛盾；
- 使用静态法律库匹配法条，并避免用“手机/财物”等泛化词误命中盗窃条款；
- Judge Agent 负责反方 challenge；
- Review Agent 负责边界复核。

## 快速运行

```powershell
cd F:\汇报\agent_demo
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
- [用户手册](USER_MANUAL.md)
- [面向领导的系统使用说明](LEADER_USER_MANUAL.md)
- [技术架构](TECHNICAL_ARCHITECTURE.md)
- [流程说明](WORKFLOW.md)

## 研判报告格式

报告类材料放入 `evidence_vault/report_images/`。该目录支持图片、Word 和 PDF：图片默认调用 Qwen 视觉模型，`.docx` 直接读取文本，`.pdf` 优先读取文本层；扫描版 PDF 请在 `evidence_vault/extracted/` 放入同名 `.txt`。

## 当前法律库匹配规则

`LegalRetrievalTool` 读取 `legal_library/laws.jsonl`。同类案件法条可按案件类型和关键词命中；跨类型法条需要更强行为要素。比如“摔坏手机、屏幕损坏”会优先关联故意毁坏财物类依据，不会仅因出现“手机/财物”就匹配盗窃条款。
