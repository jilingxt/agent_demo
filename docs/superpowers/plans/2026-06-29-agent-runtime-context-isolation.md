# Agent Runtime 与上下文隔离重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在 experiment 分支中重构 agent 运行时，让 PlanningAgent 先盘点待识别材料数量，并确保每份笔录、每组图片都在独立上下文中完成提取，减少上下文污染。

**架构：** 保留当前可稳定运行的 deterministic fallback，同时新增统一的 agent runtime 层。真实 LLM 调用通过独立 prompt 文件和 DSV4/Qwen client 进入运行时；如果 API 未配置、返回格式错误或调用失败，则回退到现有规则逻辑，保证 demo 仍可运行。

**技术栈：** Python dataclass、LangChain Runnable、现有 `Dsv4Client`、`QwenVisionClient`、`PromptLoader`、`unittest`。

---

## 一、核心设计

### 1. 材料盘点先行

任务开始时，`PlanningAgent` 不只判断案件类型，还要先生成材料盘点：

- 有多少份笔录需要提取；
- 有多少个报告图片组需要识别；
- 有多少个辨认/证据图片组需要识别；
- 每个材料或图片组的 `material_id`、来源路径、材料类型；
- 哪些材料缺少可读取内容，需要进入 Qwen 视觉或人工补录流程。

这一步的输出不直接进入最终法律分析，只作为 workflow 的调度清单。

### 2. 笔录独立上下文

`TextAgent` 处理每份笔录时必须使用独立上下文：

- 一次调用只输入一份笔录；
- prompt 中只包含该笔录文本和该笔录的元数据；
- 不传入其他笔录、图片、案件总结或历史提取结果；
- 输出只允许包含来自当前笔录的事实；
- 每条 fact 必须带当前 `material_id`。

这样可以避免 A 笔录中的人物、时间、行为污染 B 笔录。

### 3. 图片按文件夹形成独立图片组上下文

图片证据采用文件夹隔离：

```text
evidence_vault/
  identification_images/
    group_001/
      1.jpg
      2.jpg
    group_002/
      a.png
  report_images/
    report_001/
      page1.jpg
      page2.jpg
```

规则：

- 同一个子文件夹表示同一件事或同一份报告的一组图片；
- 一个图片组作为一次独立 Qwen 视觉上下文；
- Qwen 可以在组内比较多张图，但不能看到其他文件夹的图片；
- 图片组输出一个结构化描述，后续 `PicAgent` 或 `ReportImageAgent` 再把描述转成 facts；
- 单张散放图片继续兼容为一个单图组。

### 4. Prompt 文件真正进入运行时

已有 prompt 文件继续保留，但要让文本类 agent 真正通过 runtime 加载：

- `planning_agent.md`
- `text_agent.md`
- `report_image_agent.md`
- `conflict_agent.md`
- `reasoning_agent.md`
- `judge_agent.md`
- `review_agent.md`
- `pic_agent_qwen.md`

其中：

- DSV4 agent 使用 `Dsv4Client + PromptLoader`；
- Qwen 图片组使用 `QwenVisionClient + PromptLoader`；
- `LegalRetrievalTool` 继续是工具，不改成 prompt agent。

---

## 二、文件改动范围

### 新增文件

- `case_agent_demo/agent_runtime.py`
  - 统一封装 prompt 加载、LLM 调用、JSON 解析、fallback 调用。
- `case_agent_demo/material_plan.py`
  - 定义材料盘点结构，如 `MaterialPlan`、`MaterialTask`、`ImageGroupTask`。
- `tests/test_agent_runtime.py`
  - 测试 prompt 加载、fallback、JSON 解析失败回退。
- `tests/test_material_planning.py`
  - 测试 PlanningAgent 的材料盘点输出。
- `tests/test_context_isolation.py`
  - 测试每份笔录和每个图片组不会共享上下文。

### 修改文件

- `case_agent_demo/evidence_intake.py`
  - 支持图片子文件夹分组；
  - 保持散放图片兼容；
  - manifest 记录 `group_id`。
- `case_agent_demo/agents.py`
  - 将各 agent 的规则逻辑改成 fallback；
  - 文本类 agent 可选择通过 runtime 调用真实 LLM；
  - `PlanningAgent` 增加材料盘点能力。
- `case_agent_demo/vision_tools.py`
  - 增加图片组描述接口；
  - 单图描述继续兼容。
- `case_agent_demo/workflow.py`
  - 先执行材料盘点；
  - 按材料盘点逐个调度 TextAgent；
  - 按图片组逐组调度 PicAgent/ReportImageAgent；
  - 后续再合并 Case Graph。
- `case_agent_demo/models.py`
  - 如果需要，补充 `group_id`、`plan_id` 等字段。
- `USER_MANUAL.md`
  - 说明图片组目录组织方式。
- `TECHNICAL_ARCHITECTURE.md`
  - 说明上下文隔离和 runtime fallback 架构。

---

## 三、任务拆解

### Task 1：定义材料盘点模型

**文件：**
- 新增：`case_agent_demo/material_plan.py`
- 测试：`tests/test_material_planning.py`

- [ ] **Step 1：写失败测试**

测试目标：

- 两份笔录生成两个独立 statement task；
- 两个图片文件夹生成两个 image group task；
- 每个 task 都保留来源路径和材料类型。

- [ ] **Step 2：实现最小模型**

新增结构：

- `MaterialTask`
- `ImageGroupTask`
- `MaterialPlan`

字段至少包括：

- `task_id`
- `material_type`
- `material_ids`
- `source_paths`
- `group_id`
- `requires_vision`

- [ ] **Step 3：运行测试**

命令：

```powershell
python -m unittest tests.test_material_planning -v
```

预期：新增测试通过。

### Task 2：重构 EvidenceIntake 支持图片组

**文件：**
- 修改：`case_agent_demo/evidence_intake.py`
- 测试：`tests/test_evidence_intake.py`

- [ ] **Step 1：写图片组测试**

测试场景：

```text
identification_images/
  group_a/
    1.jpg
    2.jpg
  single.jpg
```

预期：

- `group_a` 被识别为一个图片组；
- `single.jpg` 被兼容为一个单图组；
- manifest 写入 `group_id`。

- [ ] **Step 2：实现分组扫描**

实现规则：

- 子文件夹内图片按文件名排序；
- 一级目录图片作为单图组；
- 不跨文件夹合并图片。

- [ ] **Step 3：运行 intake 测试**

命令：

```powershell
python -m unittest tests.test_evidence_intake -v
```

### Task 3：新增 AgentRuntime

**文件：**
- 新增：`case_agent_demo/agent_runtime.py`
- 测试：`tests/test_agent_runtime.py`

- [ ] **Step 1：写 fallback 测试**

场景：

- API client 不存在时，runtime 调用 fallback；
- LLM 返回非 JSON 时，runtime 调用 fallback；
- prompt 文件缺失时，明确抛出配置错误或回退，二者选一种并测试。

建议选择：prompt 缺失时抛出清晰错误，因为这是配置问题。

- [ ] **Step 2：实现 runtime**

核心接口建议：

```python
class AgentRuntime:
    def run_json(
        self,
        prompt_name: str,
        profile: ModelProfile,
        user_input: str,
        fallback: Callable[[], T],
        parser: Callable[[dict[str, Any]], T],
    ) -> T:
        ...
```

- [ ] **Step 3：运行 runtime 测试**

命令：

```powershell
python -m unittest tests.test_agent_runtime -v
```

### Task 4：PlanningAgent 增加材料盘点

**文件：**
- 修改：`case_agent_demo/agents.py`
- 修改：`case_agent_demo/workflow.py`
- 测试：`tests/test_material_planning.py`
- 测试：`tests/test_workflow.py`

- [ ] **Step 1：写 workflow 测试**

验证：

- workflow 在正式提取前先调用 PlanningAgent 的材料盘点；
- `WorkflowResult` 或中间状态能看到材料数量；
- 未经人工确认案件类型时仍不进入后续分析。

- [ ] **Step 2：实现 `PlanningAgent.plan_materials`**

行为：

- 输入 `list[Material]`；
- 输出 `MaterialPlan`；
- 不做案件事实推理；
- 不合并不同笔录上下文。

- [ ] **Step 3：运行 workflow 测试**

命令：

```powershell
python -m unittest tests.test_material_planning tests.test_workflow -v
```

### Task 5：TextAgent 独立上下文提取

**文件：**
- 修改：`case_agent_demo/agents.py`
- 测试：`tests/test_context_isolation.py`

- [ ] **Step 1：写上下文隔离测试**

构造两份笔录：

- `S1` 包含张三；
- `S2` 包含李四；

验证：

- 处理 `S1` 时 runtime user input 不包含 `S2` 文本；
- 处理 `S2` 时 runtime user input 不包含 `S1` 文本；
- 输出 fact 的 `source_material_id` 分别正确。

- [ ] **Step 2：实现 TextAgent runtime 接入**

原则：

- 每次 `extract(material)` 只生成该 material 的 user input；
- fallback 保留现有规则提取；
- LLM 解析失败时 fallback。

- [ ] **Step 3：运行隔离测试**

命令：

```powershell
python -m unittest tests.test_context_isolation -v
```

### Task 6：Qwen 图片组独立上下文识别

**文件：**
- 修改：`case_agent_demo/vision_tools.py`
- 修改：`case_agent_demo/agents.py`
- 测试：`tests/test_vision_tools.py`
- 测试：`tests/test_context_isolation.py`

- [ ] **Step 1：写图片组上下文测试**

构造：

- `group_a` 两张图片；
- `group_b` 一张图片；

验证：

- 发送给 Qwen 的 payload 中，`group_a` 只包含 `group_a` 的图片；
- `group_b` 不会看到 `group_a` 的图片；
- 每组输出一个独立描述。

- [ ] **Step 2：实现 `describe_group`**

建议接口：

```python
def describe_group(self, group_id: str, image_paths: list[str]) -> ImageEvidenceDescription:
    ...
```

兼容：

- `describe(material)` 继续保留；
- 单图 material 内部可包装成单图 group。

- [ ] **Step 3：运行视觉测试**

命令：

```powershell
python -m unittest tests.test_vision_tools tests.test_context_isolation -v
```

### Task 7：Reasoning/Judge/Review 接入 runtime，但保持边界

**文件：**
- 修改：`case_agent_demo/agents.py`
- 测试：`tests/test_workflow.py`
- 测试：`tests/test_agent_runtime.py`

- [ ] **Step 1：写边界测试**

验证：

- Reasoning 的输入只能来自 Case Graph、Conflict、LegalMatch；
- Judge 只 challenge，不输出最终裁判；
- Review 继续拦截最终性法律判断。

- [ ] **Step 2：接入 prompt**

接入：

- `reasoning_agent.md`
- `judge_agent.md`
- `review_agent.md`

保留：

- 当前 deterministic 输出作为 fallback；
- forbidden phrase 检查仍在 ReviewAgent 中硬编码保底。

- [ ] **Step 3：运行工作流测试**

命令：

```powershell
python -m unittest tests.test_workflow tests.test_agent_runtime -v
```

### Task 8：文档同步

**文件：**
- 修改：`USER_MANUAL.md`
- 修改：`TECHNICAL_ARCHITECTURE.md`
- 修改：`WORKFLOW.md`

- [ ] **Step 1：更新用户手册**

说明：

- 笔录每份独立提取；
- 图片按子文件夹分组；
- PlanningAgent 会先盘点材料数量；
- API 配置仍使用 `config/api_keys.toml`。

- [ ] **Step 2：更新技术文档**

说明：

- `AgentRuntime`;
- prompt 文件进入运行时；
- fallback 机制；
- 上下文隔离边界。

- [ ] **Step 3：扫描旧表述**

命令：

```powershell
rg -n "<old-qwen-flag>|<old-local-image-processing-field>|<old-env-loader>" . --glob "!external/**"
```

预期：无旧口径命中。

### Task 9：最终验证与实验提交

**文件：**
- 不限定。

- [ ] **Step 1：完整测试**

命令：

```powershell
python -m unittest discover -s tests -v
```

预期：全部通过。

- [ ] **Step 2：样例运行**

命令：

```powershell
python -m case_agent_demo.cli --sample
```

预期：输出案件类型建议、材料清单、模型配置、Judge challenge、最终报告、Review 结果。

- [ ] **Step 3：查看 diff**

命令：

```powershell
git status --short
git diff --stat
```

- [ ] **Step 4：提交实验分支**

命令：

```powershell
git add .
git commit -m "refactor: isolate agent contexts and wire prompt runtime"
```

---

## 四、验收标准

- PlanningAgent 在提取前能输出材料盘点。
- 每份笔录一次独立 TextAgent 调用，不共享其他笔录上下文。
- 同一文件夹内图片作为一个 Qwen 视觉上下文，不跨文件夹污染。
- prompt 文件不再只是静态文档，文本类 agent 至少通过统一 runtime 具备调用能力。
- API 缺失或 LLM 输出异常时，demo 仍能通过 fallback 跑通。
- 全量单元测试通过。
- 样例 CLI 通过。
