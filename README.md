# Case Agent Demo

一个用于案件笔录、图片证据、报告图片和静态法律库协同分析的多 Agent demo。

## 核心能力

- 读取 `evidence_vault` 中的笔录、证据图片、报告图片；
- 使用 Qwen Vision 描述图片证据并识别图片文字；
- 使用 DeepSeek 文本模型 profile 区分高/低推理任务；
- 构建 Case Graph；
- 独立检测冲突；
- 使用静态法律库匹配法条；
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
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "盗窃类案件"
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
- [技术架构](TECHNICAL_ARCHITECTURE.md)
- [流程说明](WORKFLOW.md)

## 研判报告格式

报告类材料放入 `evidence_vault/report_images/`。该目录支持图片、Word 和 PDF：图片默认调用 Qwen 视觉模型，`.docx` 直接读取文本，`.pdf` 优先读取文本层；扫描版 PDF 请在 `evidence_vault/extracted/` 放入同名 `.txt`。
