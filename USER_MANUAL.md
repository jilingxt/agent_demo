# 用户手册

## 1. 快速开始

进入项目并安装：

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

`--sample` 只演示流程结构，不读取真实证据目录，也不会调用真实 LLM。

## 2. 接入 API

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
model_name = "qwen2.5-vl-72b-instruct"
timeout_seconds = 120
```

真实 key 文件已被 `.gitignore` 忽略，不要写入 Markdown、测试或代码。

如果 Qwen 返回 `HTTP 403 Forbidden` 或 `access_denied`，通常是账号、模型权限或 endpoint 不匹配。可以在阿里云控制台开通对应视觉模型，或把 `[qwen].base_url` 改成控制台给出的 OpenAI 兼容地址。临时测试时也可以把 `model_name` 改成账号已有权限的视觉模型。

## 3. 初始化证据文件夹

```powershell
python -m case_agent_demo.cli --init-evidence-vault evidence_vault
```

目录结构：

```text
evidence_vault/
  statements/             # 笔录：.txt / .docx / .pdf
  report_images/          # 研判报告、法医检测报告：.jpg / .jpeg / .png / .docx / .pdf
  identification_images/  # 图片辨认、现场照片、证据照片：.jpg / .jpeg / .png
  extracted/              # 人工修正文本，优先覆盖自动识图或文本层结果
  manifest.json           # 自动生成的证据清单
```

本项目不在本地做 OCR。图片理解交给 Qwen 视觉 API；Word 读取文本；PDF 优先读取文本层。扫描版 PDF 或识别结果需要修正时，在 `extracted/` 放同名 `.txt`。

## 4. 放置材料

笔录放入：

```text
evidence_vault/statements/
```

研判报告、法医检测报告等报告类材料放入：

```text
evidence_vault/report_images/
```

现场照片、辨认图片、证据照片放入：

```text
evidence_vault/identification_images/
```

同一件事、同一次辨认、同一份报告的多张图片，建议放在同一个子文件夹中。系统会把同一个子文件夹作为一次 Qwen 视觉上下文处理，不同文件夹不会互相看到：

```text
evidence_vault/
  identification_images/
    group_001/
      1.jpg
      2.jpg
  report_images/
    report_001/
      page1.jpg
      page2.jpg
```

人工修正文本示例：

```text
evidence_vault/identification_images/P1.jpg
evidence_vault/extracted/P1.txt
```

运行时会优先使用 `extracted/P1.txt`。

## 5. 运行真实分析

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "故意伤害类案件"
```

`--case-type` 是人工确认后的案件类型。没有人工确认案件类型时，后续 Agent 不会继续执行。

真实证据目录默认调用 Qwen Vision 处理图片材料。如果只想排查文本流程：

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "故意伤害类案件" --disable-qwen-vision
```

## 6. TextAgent 如何处理笔录

`TextAgent` 每次只接收一份笔录，独立提取结构化事实，不会把其他笔录、图片描述或历史结果混入同一次上下文。

写入 Case Graph 的不是原始笔录全文，而是类似下面的事实：

```text
person=李文杰
time=2026年6月12日
location=深圳市宝安区新凯飞汽配
behavior=李文杰摔坏手机
object=手机
```

否认类陈述也会作为独立事实进入 Case Graph，例如“李文杰称没有打架”“贺显作称没有动手”。这些事实会供 `ConflictAgent` 与验伤报告、图片、研判报告等材料交叉检查。

## 7. 静态法律库

法律库位置：

```text
legal_library/laws.jsonl
```

每行一条 JSON：

```json
{"law_id":"criminal_law_264","law_name":"中华人民共和国刑法","article":"第二百六十四条","text":"盗窃公私财物，数额较大的，或者多次盗窃、入户盗窃、携带凶器盗窃、扒窃的，依法处理。","legal_elements":["非法占有目的","秘密窃取","公私财物"],"keywords":["盗窃","窃取","秘密窃取","非法占有","拿走"],"case_types":["盗窃类案件"],"effective_status":"effective","source":"static_law_library"}
```

建议把关键词写成法律构成要件或强行为词，不要只写“手机、财物、人员、现场”这类泛化词。当前检索逻辑会避免仅因“摔坏手机”中的“手机/财物”误命中盗窃条款；盗窃条款需要出现“盗窃、偷、窃取、拿走、非法占有”等更强语义。

## 8. 调整 Prompt 和参数

Prompt 文件在：

```text
config/prompts/
```

常用文件：

```text
text_agent.md          # 单份笔录事实抽取
pic_agent_qwen.md      # 图片证据描述与文字识别
report_image_agent.md  # 报告类材料事实提炼
conflict_agent.md      # 独立冲突检测
reasoning_agent.md     # 辅助分析报告
judge_agent.md         # 反方 challenge
review_agent.md        # 证据边界和法律依据边界复核
```

修改 prompt 后直接重新运行项目即可。DeepSeek 文本模型默认在 `case_agent_demo/config.py` 中配置；Qwen 视觉模型、base URL、timeout 等运行参数可在 `config/api_keys.toml` 中调整。

## 9. 常见问题

缺少 API key：

```text
provider.api_key is required in config/api_keys.toml
```

检查 `config/api_keys.toml` 是否存在并已填写。

图片没有自动识别：

- 确认没有使用 `--disable-qwen-vision`；
- 确认 `config/api_keys.toml` 中 `[qwen]` 已填写；
- 如果有 `extracted/同名.txt`，系统会优先使用人工文本。

法条匹配到不相关内容：

- 检查 `legal_library/laws.jsonl` 的 `keywords` 是否过于泛化；
- 盗窃类条款不要只用“手机、财物”作为关键词；
- 故意毁坏财物类事实建议包含“损坏、摔坏、毁坏、砸坏”等词。

## 10. 本次更新说明（v0.51）

v0.51 保留原来的使用方式，同时新增法律知识库、证据图谱 claim、置信度提示和最终审查问题。

### 10.1 版本确认

项目版本已更新为：

```text
0.51.0
```

可以在 `pyproject.toml` 中查看。

### 10.2 使用法律知识库

新增本地法律知识库目录：

```text
legal_knowledge/
  incoming/   # 放入待入库文件
  active/     # 预留目录
  archived/   # 预留目录
  metadata/   # 预留目录
  index/      # 自动生成索引
```

支持放入以下文件：

- `.txt`
- `.md`
- 旧版 `.jsonl` 法律库文件

程序会把文件切分为 chunk，并生成：

```text
legal_knowledge/index/documents.jsonl
legal_knowledge/index/chunks.jsonl
```

普通用户不需要手工修改 `index/` 里的文件。需要更新知识库时，把新文件放入 `legal_knowledge/incoming/`，由程序重新入库即可。

如果没有配置或没有内容，系统仍会回退读取旧的：

```text
legal_library/laws.jsonl
```

### 10.3 查看置信度

v0.51 中，系统会在证据图谱中生成 `EvidenceClaim`，并为每个 claim 生成置信度提示。

常见标签含义如下：

| 标签 | 含义 |
| --- | --- |
| 多源较强印证 | 多份材料相互支持，可信程度较高 |
| 有一定印证 | 有支持材料，但仍建议结合上下文复核 |
| 争议事实，尚不足以否定 | 存在反向说法，但支持材料仍有一定基础 |
| 明显存疑，需补强 | 支持不足或冲突明显，需要补充核实 |
| 低可信或被冲突削弱 | 当前材料不宜直接采信，应重点复核 |

注意：置信度不是法律结论，只是帮助用户找到需要重点复核的事实。

### 10.4 查看最终审查问题

v0.51 新增 `FinalConflictAgent`。它会在流程后段生成审查问题，常见类型包括：

- 证据冲突；
- 证据不足；
- 法律依据缺失；
- 报告表述越界；
- 图片证据置信度偏低。

这些问题会兼容进入原来的 challenge / review 流程。用户看到这类提示时，应回到原始材料核对，不要只看 AI 的文字结论。

### 10.5 推荐使用流程

1. 初始化证据文件夹。
2. 放入笔录、图片、报告等案件材料。
3. 如需扩展法律依据，把 `.txt`、`.md` 或 `.jsonl` 文件放入 `legal_knowledge/incoming/`。
4. 运行程序，并人工确认案件类型。
5. 查看系统输出的事实、冲突、法律依据、置信度和审查问题。
6. 对“明显存疑”“需补强”“报告越界”等提示逐项人工复核。

### 10.6 重要提醒

系统不会替代人工定性、事实采信或最终处理决定。对于真实案件，用户必须结合原始材料、法定程序、证据规则和单位要求进行审核。
