# 流程说明

## 1. 总体流程

```mermaid
flowchart TD
  A["用户放入证据材料"] --> B["EvidenceIntake"]
  B --> C["PlanningAgent 建议案件类型"]
  C --> D["人工确认案件定性"]
  D --> E["TextAgent 处理笔录"]
  D --> F["PicAgent 处理证据图片"]
  D --> G["ReportImageAgent 处理报告图片"]
  F --> H["QwenImageEvidenceTool"]
  G --> H
  E --> I["EvidenceGraphAgent / Case Graph"]
  F --> I
  G --> I
  I --> J["ConflictAgent"]
  I --> K["LegalRetrievalTool"]
  J --> L["ReasoningAgent"]
  K --> L
  L --> M["JudgeAgent"]
  M --> N["ReasoningAgent 修订"]
  N --> O["ReviewAgent"]
  O --> P["输出辅助分析报告"]
```

## 2. 配置流程

```mermaid
flowchart LR
  A["config/api_keys.toml"] --> B["API Client"]
  C["config/prompts/*.md"] --> D["PromptLoader"]
  B --> E["Agent / Tool"]
  D --> E
```

## 3. 人工门

PlanningAgent 只提出案件类型建议。用户必须传入或确认 `--case-type` 后，后续 Agent 才执行。

## 4. 图片证据

真实证据目录默认调用 Qwen Vision。人工修正文本可写入 `evidence_vault/extracted/同名.txt`，系统会优先使用人工文本。

## 5. 输出边界

报告只作为辅助分析，不输出最终定罪、处罚、责任承担等结论。
