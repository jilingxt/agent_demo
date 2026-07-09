# 项目技术架构

## 1. 当前定位

本项目是 Python + LangChain Core 搭建的多 Agent 案件证据分析 demo。它面向真实 LLM 接入，支持 DeepSeek 文本模型、Qwen 视觉模型、证据文件夹、静态法律库、Case Graph、Conflict、Judge challenge 和 Review。

当前法律依据检索是 `LegalRetrievalTool` 读取静态 JSONL 法律库，不是向量 RAG，也不是独立 Rag Agent。后续如果升级向量检索，应优先把 retriever 接到这个工具接口后面。

## 2. 核心目录

```text
case_agent_demo/
  agents.py           # Planning/Text/Pic/Report/Conflict/EvidenceGraph/Reasoning/Judge/Review
  workflow.py         # CaseWorkflow 编排
  models.py           # Material、Fact、CaseGraph、LegalMatch 等数据结构
  evidence_intake.py  # 证据文件夹扫描与材料读取
  tools.py            # LegalRetrievalTool / RagLegalAgent 兼容包装
  config.py           # 模型 profile
  llm_clients.py      # OpenAI-compatible API client
  prompt_config.py    # PromptLoader
  vision_tools.py     # Qwen 图片证据工具
  cli.py              # 命令行入口

config/
  api_keys.example.toml
  api_keys.toml       # 本地真实 key，已忽略
  prompts/

legal_library/
  laws.jsonl          # 静态法律库
```

## 3. 模型分工

| 模块 | 推荐模型 / 工具 |
| --- | --- |
| Planning | deepseek-v4-pro |
| Text | deepseek-v4-flash，失败时走规则 fallback |
| Pic / Vision | qwen2.5-vl-72b-instruct 或账号有权限的 Qwen VL 模型 |
| ReportImage | Qwen VL + deepseek-v4-pro，文档文本可直接读取 |
| EvidenceGraph | 结构化合并 |
| Conflict | deepseek-v4-pro 或规则 fallback |
| Legal Retrieval | 静态 JSONL 检索工具 |
| Reasoning | deepseek-v4-pro |
| Judge | deepseek-v4-pro |
| Review | deepseek-v4-pro |

## 4. 配置流

```mermaid
flowchart TD
  A["config/api_keys.toml"] --> B["ApiClientConfig.from_file"]
  B --> C["Dsv4Client"]
  B --> D["QwenVisionClient"]
  E["config/prompts/*.md"] --> F["PromptLoader"]
  F --> G["AgentRuntime"]
  C --> G
  D --> H["QwenImageEvidenceTool"]
  F --> H
```

## 5. 证据流

```mermaid
flowchart TD
  A["evidence_vault/statements"] --> B["TextAgent: 单份笔录事实提炼"]
  C["evidence_vault/report_images"] --> D["ReportImageAgent: 报告事实提炼"]
  E["evidence_vault/identification_images"] --> F["PicAgent: 图片事实提炼"]
  F --> G["QwenImageEvidenceTool"]
  D --> G
  B --> H["EvidenceGraphAgent / Case Graph"]
  F --> H
  D --> H
  H --> I["ConflictAgent"]
  H --> J["LegalRetrievalTool"]
  I --> K["ReasoningAgent"]
  J --> K
  K --> L["JudgeAgent"]
  L --> M["ReasoningAgent 修订"]
  M --> N["ReviewAgent"]
```

## 6. Agent Runtime 与上下文隔离

`AgentRuntime` 统一处理 prompt 加载、OpenAI-compatible 调用、JSON 解析和 fallback。文本类 Agent 可以选择注入 runtime；未注入 runtime、API 不可用或返回内容无法解析时，系统回退到规则逻辑，保证 demo 可离线运行。

`PlanningAgent` 在执行分析前生成 `MaterialPlan`。该计划记录 statement task、evidence image group task、report image group task，作为后续调度依据。

上下文隔离规则：

- `TextAgent` 每次只处理一个 statement material；
- `PicAgent` 在 Qwen 可用时按图片文件夹调用 `describe_group`；
- `ReportImageAgent` 在 Qwen 可用时按报告图片文件夹调用 `describe_group`；
- `ReasoningAgent` 的 runtime 输入只来自 Case Graph、Conflict 和 LegalMatch，不接收原始材料全集。

## 7. TextAgent 事实提炼

`TextAgent` 的目标是把单份笔录提炼为 `Fact`，而不是把整段问答写入数据库。`Fact` 包含：

```text
fact_id
source_material_id
source_type
person
behavior
time
location
object
confidence
```

当前规则 fallback 会优先识别：

- 暴力/伤害行为，例如拉拽、抱摔、掐脖子及伤情后果；
- 财物损坏行为，例如摔坏手机、砸坏门锁、屏幕损坏；
- 财物转移行为，例如拿走、窃取；
- 否认类陈述，例如没有打架、没有动手、没有拿、没有损坏、没有受伤。

否认类事实会保留为独立 `Fact`，供 `ConflictAgent` 与报告、图片、物证事实交叉检测。

## 8. 静态法律库检索

`LegalRetrievalTool` 从 `legal_library/laws.jsonl` 读取法条，输出 `LegalMatch`。当前不是向量 RAG。

匹配策略：

- 案件类型匹配的法条可以按较低阈值命中；
- 跨案件类型法条必须有更强关键词或构成要素命中；
- 盗窃条款需要“盗窃、偷、窃取、拿走、非法占有、秘密窃取”等强语义；
- “手机、财物、物品、现场、人员”等泛化词不会单独触发跨类型法条；
- “摔坏、损坏、毁坏、砸坏、屏幕损坏”等上下文可关联故意毁坏财物类依据。

这可以避免“手机被摔坏”仅因包含“手机/财物”而误匹配刑法第二百六十四条盗窃罪。

## 9. 报告材料接入

`evidence_vault/report_images/` 是报告类材料入口，不再只表示图片目录：

- `.jpg` / `.jpeg` / `.png`：进入 `ReportImageAgent`，通过 Qwen 视觉模型生成图片描述和文字识别结果；
- `.docx`：由证据导入层直接提取 Word 文本，生成报告类 `Material`；
- `.pdf`：优先提取 PDF 文本层；扫描版或不可提取文本的 PDF 使用 `evidence_vault/extracted/<同名>.txt` 作为人工文本覆盖。

系统不在本地运行 OCR。图片理解交给 Qwen API，文档文本只读取可解析文本层或人工提供的同名文本。

## 10. 关键边界

- Planning 只能建议案件类型，执行前必须有人确认案件定性；
- Reasoning 只能基于 Case Graph、Conflict、LegalMatch 输出；
- Judge 只负责 challenge，不作最终裁判；
- Review 拦截最终性法律判断和超出证据/法条边界的表述；
- API key 只放在 `config/api_keys.toml`；
- Prompt 放在 `config/prompts/`，不硬编码在 Agent 中。

## 11. 本次更新说明（v0.51）

本次 v0.51 更新是在原有多 Agent 案件证据分析流程上，增加“证据图谱、事实主张、置信度、法律知识库和最终冲突审查”能力。原有 `Fact`、`LegalRetrievalTool.retrieve(payload)`、工作流输出结构和既有 Agent 入口仍保留，确保旧流程可以继续运行。

### 11.1 使用的主要技术

本项目仍采用 Python 作为主体语言，使用标准库 `dataclasses` 定义结构化数据模型，用 `unittest` 做回归测试，用本地 JSONL 文件保存轻量索引和知识库数据。项目不依赖外部向量数据库，不把真实 API key 写入代码或文档。

LLM 接入仍保持 OpenAI-compatible API 方式：

- DeepSeek 文本模型：用于笔录提炼、冲突分析、辅助推理、报告草拟和复核；
- Qwen 视觉模型：用于图片证据、报告图片、扫描材料的视觉理解；
- 本地 fallback 规则：在没有真实模型或模型返回异常时，保证 demo 流程仍可运行。

法律知识检索从单一静态 `legal_library/laws.jsonl` 扩展为两层结构：

- `LegalKnowledgeBaseTool`：支持 `.txt`、`.md`、旧版 `.jsonl` 文件入库，生成本地 `documents.jsonl` 和 `chunks.jsonl` 索引；
- `LegalRetrievalTool`：继续保留旧接口，优先调用 `LegalKnowledgeBaseTool`，知识库为空时回退到原静态法律库。

### 11.2 EvidenceGraph 与 EvidenceClaim

v0.51 对 `EvidenceNode` 和 `EvidenceEdge` 增加了更多审查字段，例如：

- `polarity`：事实倾向，区分肯定、否认等；
- `claim_type`：主张类型，例如伤害、财产损毁、盗窃、程序审查等；
- `source_party`：事实来源方；
- `observation_type`：事实来源类型，如笔录、图片、报告；
- `status` 和 `version`：为后续人工修订、软删除和版本追踪预留。

新增 `EvidenceClaim` 用于把多个证据节点聚合成“一个待审查事实主张”。例如，多份笔录、图片说明、鉴定报告都指向同一伤害事实时，会被汇总到同一个 claim；否认类陈述会作为反向证据进入同一 claim。

### 11.3 ConfidenceEngine 置信度计算

新增 `ConfidenceEngine`，用于给 claim 级事实生成综合置信度。它不是司法证明概率，也不是最终裁判结论，而是一个辅助排序和风险提示指标。

计算时主要考虑：

- 支持证据数量；
- 反向证据数量；
- 证据来源可靠性，例如报告类材料通常高于普通陈述；
- 来源是否多元；
- 是否存在相互冲突或低质量材料。

输出结果包括：

- `score`：0 到 1 的数值；
- `label`：如“多源较强印证”“有一定印证”“争议事实，尚不足以否定”“明显存疑，需补强”等；
- `reasons`：简要解释评分依据。

### 11.4 LegalKnowledgeBaseTool 与领域亲和度

新增 `legal_kb.py` 和 `domain_affinity.py`：

- `LegalKnowledgeBaseTool` 负责本地法律知识文件入库、切片、更新、软删除和检索；
- `DomainAffinityIndexer` 根据关键词和文本内容计算法律领域亲和度；
- `CaseDomainRouter` 根据案件类型和证据图谱推断检索优先领域。

当前实现是轻量关键词检索和领域加权，不是完整向量 RAG。后续如果接入 embedding、rerank 或向量数据库，可以优先接在 `LegalKnowledgeBaseTool.search()` 后面，不需要改动旧工作流入口。

### 11.5 FinalConflictAgent 最终审查

新增 `FinalConflictAgent`，位于报告生成前后的边界审查环节。它统一识别：

- 证据之间存在直接冲突；
- claim 置信度不足；
- 法律依据缺失；
- 报告表述超出证据或法条边界；
- 图片类证据置信度偏低，需要人工核验。

该模块输出 `ValidationIssue`，并兼容转换为原来的 `Challenge`，所以旧的 Judge/Review 机制仍然可以继续使用。

### 11.6 v0.51 后的主要流程

```mermaid
flowchart TD
  A["证据材料"] --> B["Planning Agent"]
  B --> C["Text / Pic / Report Agent"]
  C --> D["GraphStore 增量写入节点和边"]
  D --> E["EvidenceGraph"]
  E --> F["ClaimBuilder 聚合 EvidenceClaim"]
  F --> G["ConfidenceEngine 计算 claim 置信度"]
  E --> H["LegalKnowledgeBaseTool 检索法律依据"]
  G --> I["Reasoning / Judge / Review"]
  H --> I
  I --> J["FinalConflictAgent 最终审查"]
  J --> K["辅助分析报告和审查问题"]
```

### 11.7 仍然保留的边界

v0.51 仍是 demo 级实现，不输出最终定罪或裁判结论。系统只做材料整理、事实抽取、矛盾提示、法律依据辅助检索和报告边界审查。案件类型确认、事实采信、法律定性和处理决定必须由具备权限的人员完成。
