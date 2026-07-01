# Tests 目录说明

本项目测试基于 Python 标准库 `unittest`。

运行命令：

```powershell
python -m unittest discover -s tests -v
```

当前全量测试覆盖 69 个用例。

## 覆盖重点

| 测试文件 | 主要覆盖 |
| --- | --- |
| `test_agent_person_extraction.py` | TextAgent / ReportImageAgent 的人员抽取 |
| `test_agent_runtime.py` | AgentRuntime、prompt 加载、JSON 解析和 fallback |
| `test_cli_qwen_vision.py` | CLI 中 Qwen 视觉默认启用、禁用和注入逻辑 |
| `test_context_isolation.py` | 笔录单份上下文、图片单组上下文、Reasoning 输入边界 |
| `test_evidence_intake.py` | 证据目录初始化，`.txt` / `.docx` / `.pdf` / 图片材料加载 |
| `test_fact_refinement.py` | Text/Pic/Report Agent 入图前事实提炼，不复制全文 |
| `test_general_conflict_agent.py` | ConflictAgent 泛化冲突检测：伤害、拿取、损坏等 |
| `test_legal_library.py` | 静态法律库检索、demo fallback、盗窃条款误命中过滤 |
| `test_llm_clients.py` | DeepSeek/Qwen OpenAI-compatible payload 和错误脱敏 |
| `test_material_planning.py` | PlanningAgent 的材料盘点与任务拆分 |
| `test_open_source_stack.py` | 外部开源组件声明和“不安装、不执行”的安全边界 |
| `test_pic_agent_qwen.py` | PicAgent 与 Qwen 视觉结果集成 |
| `test_runtime_config.py` | API key 文件读取、模型覆盖、prompt 读取 |
| `test_vision_tools.py` | 图片转 data URL、Qwen JSON 解析、图片组 fallback |
| `test_workflow.py` | CaseWorkflow 端到端调度、人工案件类型门、Review 边界 |

## 最新关键回归

- `TextAgent` 不把完整笔录问答写入 `behavior`。
- `TextAgent` 能把“摔坏手机/屏幕损坏”提炼成短事实，并正确处理“我/他”的行为人。
- 否认类陈述会作为独立事实保留，供 `ConflictAgent` 检测。
- “摔坏手机”不会仅因出现“手机/财物”误匹配刑法第二百六十四条盗窃条款。
- 报告类材料支持图片、Word 和 PDF，但本地不做 OCR。
