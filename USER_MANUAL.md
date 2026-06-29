# 用户手册

## 9. 上下文隔离与图片分组

本 demo 在正式分析前会先由 `PlanningAgent` 盘点材料数量，包括笔录数量、证据图片组数量和报告图片组数量。

笔录材料按“每份笔录一个独立上下文”处理。`TextAgent` 每次只接收一份笔录的内容和元数据，不会把其他笔录、图片描述或历史提取结果放入同一次提取请求。

图片材料按文件夹分组。同一件事、同一次辨认、同一份报告的多张图片，应放在同一个子文件夹中：

```text
evidence_vault/
  identification_images/
    group_001/
      1.jpg
      2.jpg
    group_002/
      1.jpg
  report_images/
    report_001/
      page1.jpg
      page2.jpg
```

同一个子文件夹会作为一次 Qwen 视觉上下文处理；不同文件夹不会互相看到。直接放在 `identification_images/` 或 `report_images/` 下的单张图片，会被兼容为一个单图组。
## 1. 快速开始

进入项目：

```powershell
cd F:\汇报\agent_demo
pip install -e .
```

运行离线样例：

```powershell
python -m case_agent_demo.cli --sample
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## 2. 配置真实模型

复制 API 配置示例：

```powershell
Copy-Item config/api_keys.example.toml config/api_keys.toml
```

填写 `config/api_keys.toml`：

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

真实 key 文件已被 `.gitignore` 忽略。

## 3. 调整 Prompt

Prompt 文件在：

```text
config/prompts/
```

常用文件：

```text
pic_agent_qwen.md       # 图片证据描述与文字识别
reasoning_agent.md      # 推理报告
judge_agent.md          # 反方 challenge
review_agent.md         # 复核规则
```

修改后直接重新运行项目即可。

## 4. 初始化证据文件夹

```powershell
python -m case_agent_demo.cli --init-evidence-vault evidence_vault
```

目录结构：

```text
evidence_vault/
  statements/             # 笔录：.txt / .docx / .pdf
  report_images/          # 研判报告、法医检测报告图片：.jpg / .jpeg / .png
  identification_images/  # 图片辨认、现场照片、证据照片：.jpg / .jpeg / .png
  extracted/              # 人工修正文本，优先覆盖自动识图结果
  manifest.json           # 自动生成的证据清单
```

## 5. 放置材料

笔录放入：

```text
evidence_vault/statements/
```

图片报告放入：

```text
evidence_vault/report_images/
```

现场照片、辨认图片、证据照片放入：

```text
evidence_vault/identification_images/
```

如果图片识别结果需要人工修正，把同名文本写入：

```text
evidence_vault/extracted/图片文件名.txt
```

例如：

```text
evidence_vault/identification_images/P1.jpg
evidence_vault/extracted/P1.txt
```

## 6. 运行真实分析

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "盗窃类案件"
```

真实证据目录会默认调用 Qwen Vision 处理图片材料。如果只想检查文本流程：

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "盗窃类案件" --disable-qwen-vision
```

## 7. 静态法律库

法律库位置：

```text
legal_library/laws.jsonl
```

每行一条 JSON：

```json
{"law_id":"criminal_law_264","law_name":"中华人民共和国刑法","article":"第二百六十四条","text":"盗窃公私财物，数额较大的，或者多次盗窃、入户盗窃、携带凶器盗窃、扒窃的，依法处理。","legal_elements":["非法占有目的","秘密窃取","公私财物"],"keywords":["盗窃","财物"],"case_types":["盗窃类案件"],"effective_status":"effective","source":"static_law_library"}
```

## 8. 常见问题

缺少 API key：

```text
provider.api_key is required in config/api_keys.toml
```

检查 `config/api_keys.toml` 是否存在并已填写。

图片没有自动识别：

- 确认没有使用 `--disable-qwen-vision`；
- 确认 `config/api_keys.toml` 中 `[qwen]` 已填写；
- 如果有 `extracted/同名.txt`，系统会优先使用人工文本。
