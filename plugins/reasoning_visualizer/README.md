# Reasoning Visualizer Plugin

`reasoning_visualizer` 是 Va1ha11a_demo 的可移除推理可视化插件。它读取现有 `WorkflowResult` 和贝叶斯模型注册表，生成只读 JSON 快照，并通过本地网页展示证据图和贝叶斯网络。

删除整个 `plugins/reasoning_visualizer/` 目录不会影响 `case_agent_demo`。主项目不导入插件，插件只单向调用主项目公开的数据结构和 workflow。

## 功能

- 展示材料、事实、Assertion、Claim、贝叶斯派生 Claim 和 ValidationIssue；
- 展示 `source_of`、支持、反对、同事件、贝叶斯输入和审查问题等关系；
- 按模型 run 展示输入节点、中间节点、派生节点和边权重；
- 查看节点来源 Claim、模型参数、父节点贡献、运行值和参数哈希；
- 在浏览器中调整输入节点，实时重算 logistic/noisy-OR 派生值；
- 打开或保存可移植的 `.snapshot.json` 文件；
- 默认只监听 `127.0.0.1`，不会写回案件、证据图或模型参数。

## 运行内置示例

在项目根目录执行：

```powershell
python -m plugins.reasoning_visualizer --sample
```

默认地址：

```text
http://127.0.0.1:8765/
```

如果端口已占用，可以让系统选择可用端口：

```powershell
python -m plugins.reasoning_visualizer --sample --port 0
```

## 分析证据目录

```powershell
python -m plugins.reasoning_visualizer `
  --evidence-dir evidence_vault `
  --case-type "人工确认的案件类型"
```

需要调用 Qwen 处理图片时显式增加：

```powershell
--enable-qwen-vision
```

权威材料核验结果可以通过 JSON 文件传入：

```powershell
--authority-verifications authority_verifications.json
```

## 保存和重新打开快照

只生成快照：

```powershell
python -m plugins.reasoning_visualizer `
  --sample `
  --export reasoning.snapshot.json `
  --no-serve
```

重新打开：

```powershell
python -m plugins.reasoning_visualizer --snapshot reasoning.snapshot.json
```

已有 `WorkflowResult` 的调用方也可以直接生成快照：

```python
from plugins.reasoning_visualizer import build_snapshot, save_snapshot

snapshot = build_snapshot(workflow_result)
save_snapshot(snapshot, "reasoning.snapshot.json")
```

快照包含证据摘要、Claim、审查问题和模型参数，可能属于敏感案件数据。应存放在受控目录，不应上传到公开仓库。

## 快照协议

当前 `schema_version` 为 `1.0`：

```text
meta
  confirmed_case_type / executed_agents / review / model_versions

evidence
  nodes / edges / counts

bayesian
  runs[]
    model_id / version / group_key / anchor_claim_id
    nodes[] / edges[] / spec
```

插件前端只修改浏览器内的 scenario 值。保存快照时仍保留原始运行数据，不会把模拟值发布成正式贝叶斯参数。

## 测试

```powershell
python -m pytest -p no:cacheprovider plugins/reasoning_visualizer/tests -q
```

删除插件：

```powershell
Remove-Item -Recurse plugins/reasoning_visualizer
```

删除后继续运行主项目测试即可验证主项目无插件依赖：

```powershell
python -m pytest -p no:cacheprovider tests -q
```

## 第三方前端依赖

- Cytoscape.js `3.34.0`，MIT License；
- Lucide `1.24.0`，ISC License。

依赖已固定版本并存放在 `static/vendor/`，运行插件不需要 npm 或外部 CDN。许可证文本与资源文件放在同一目录。
