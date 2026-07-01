# 环境配置

## 1. 基础环境

建议使用 Python 3.11 或以上版本。

```powershell
cd F:\汇报\agent_demo
pip install -e .
```

验证本地代码：

```powershell
python -m unittest discover -s tests -v
python -m case_agent_demo.cli --sample
```

`--sample` 是离线结构样例，不读取真实模型配置。

## 2. API Key 配置

真实模型配置文件位于：

```text
config/api_keys.toml
```

如果文件不存在，可以复制示例：

```powershell
Copy-Item config/api_keys.example.toml config/api_keys.toml
```

填写：

```toml
[deepseek]
api_key = "你的 deepseek key"
base_url = "https://api.deepseek.com"
timeout_seconds = 120

[qwen]
api_key = "你的 qwen key"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
timeout_seconds = 120
```

`config/api_keys.toml` 已加入 `.gitignore`，不要把真实 key 提交到仓库。

## 3. 模型配置

模型 ID 写在：

```text
case_agent_demo/config.py
```

当前默认：

```text
DeepSeek high reasoning: deepseek-v4-pro
DeepSeek low reasoning:  deepseek-v4-flash
Qwen vision:             qwen2.5-vl-72b-instruct
```

## 4. Prompt 配置

Prompt 文件位于：

```text
config/prompts/
```

当前包含：

```text
pic_agent_qwen.md
reasoning_agent.md
judge_agent.md
review_agent.md
```

修改 prompt 后不需要改代码，重新运行即可。

## 5. 运行真实证据分析

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "盗窃类案件"
```

使用 `--evidence-dir` 时，图片材料默认调用 Qwen Vision。临时排查时可以关闭：

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "盗窃类案件" --disable-qwen-vision
```

## 6. 安全要求

- 真实 key 只写入 `config/api_keys.toml`；
- 不要把真实 key 写进 Markdown、测试、workflow-run 或代码；
- 不要把真实涉案材料提交到仓库；
- `config/api_keys.example.toml` 只能放占位符。

## Qwen 403 排查

如果调用图片材料时出现 `HTTP 403 Forbidden`，优先检查：

- `config/api_keys.toml` 中 `[qwen].api_key` 是否为阿里云 Model Studio / DashScope 可用 key；
- 当前账号是否已开通或有权限调用 `qwen2.5-vl-72b-instruct`；
- `[qwen].base_url` 是否与账号要求一致。默认值是 `https://dashscope.aliyuncs.com/compatible-mode/v1`，如果阿里云控制台提供了带 WorkspaceId 的专属兼容地址，应改成控制台给出的地址；
- 图片是否通过本地文件、`http(s)` URL 或 `data:*;base64,...` 形式传入。

代码会把服务端返回的错误码和消息打印出来，但不会打印 API key。

### Qwen 模型切换

`config/api_keys.toml` 支持在 `[qwen]` 下配置视觉模型：

```toml
[qwen]
api_key = "你的 qwen key"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
model_name = "qwen2.5-vl-72b-instruct"
timeout_seconds = 120
```

如果服务端返回 `access_denied`，说明当前账号或 endpoint 没有该模型权限。可以先在阿里云控制台开通对应模型，或临时改成账号已开通的模型，例如：

```toml
model_name = "qwen-vl-plus"
```
