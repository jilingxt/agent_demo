# 法律条文入库教程

项目现在已经支持“静态法律库”导入。当前不是向量 RAG，而是一个可审计、可编辑的 JSONL 法条库，由 `LegalRetrievalTool` 读取并匹配。

## 1. 静态法律库位置

```text
legal_library/
  laws.jsonl
```

每一行是一条法条或一个条文片段，格式是 JSON。

## 2. 添加一条法条

打开：

```text
legal_library/laws.jsonl
```

追加一行：

```json
{"law_id":"criminal_law_264","law_name":"中华人民共和国刑法","article":"第二百六十四条","text":"盗窃公私财物，数额较大的，或者多次盗窃、入户盗窃、携带凶器盗窃、扒窃的，依法处理。","legal_elements":["非法占有目的","秘密窃取","公私财物","数额较大或多次盗窃等情形"],"keywords":["盗窃","偷","窃取","秘密窃取","非法占有","拿走","扒窃","入户盗窃"],"case_types":["盗窃类案件"],"effective_status":"effective","source":"static_law_library"}
```

字段说明：

- `law_id`：唯一编号，不要重复；
- `law_name`：法律名称；
- `article`：条文号；
- `text`：条文正文或摘要；
- `legal_elements`：构成要件或审查要点；
- `keywords`：用于静态匹配的关键词；
- `case_types`：适用的案件类型；
- `effective_status`：效力状态，例如 `effective`；
- `source`：来源说明，建议写正式来源或内部编号。

## 3. 检索规则

`LegalRetrievalTool` 会读取 `laws.jsonl`，根据以下内容做简单匹配：

- 人工确认的案件类型；
- Case Graph 中的行为事实；
- `keywords`；
- `legal_elements`。

命中后返回 `LegalMatch`，供 `ReasoningAgent`、`JudgeAgent`、`ReviewAgent` 使用。没有命中时，系统会回退到 demo 预置法条，避免流程中断。

关键词建议使用构成要件或强行为词，不要只写“手机、财物、物品、人员、现场”等泛化词。当前检索逻辑会避免“摔坏手机”仅因包含“手机/财物”误命中盗窃条款；盗窃条款需要出现“盗窃、偷、窃取、拿走、非法占有”等更强语义。

## 4. 在代码里测试

```python
from case_agent_demo.tools import LegalRetrievalTool

tool = LegalRetrievalTool()
matches = tool.retrieve({
    "confirmed_case_type": "盗窃类案件",
    "behaviors": ["拿走他人手机"],
    "purpose": "manual_test",
})

for item in matches:
    print(item.law_id, item.law_name, item.article, item.source)
```

## 5. 和证据分析流程的关系

运行：

```powershell
python -m case_agent_demo.cli --evidence-dir evidence_vault --case-type "盗窃类案件"
```

流程会从 `evidence_vault` 提取证据材料，构建 Case Graph，再由 `ReasoningAgent` 调用 `LegalRetrievalTool` 从 `legal_library/laws.jsonl` 返回相关法条。

## 6. 建议先导入哪些法条

建议先放 20 到 50 条高频法条，例如盗窃、诈骗、故意毁坏财物、故意伤害、寻衅滋事、非法侵入住宅、掩饰隐瞒犯罪所得、帮助信息网络犯罪活动、妨害公务、危险驾驶等。

## 7. 后续升级到真正 RAG

静态 JSONL 跑通后，再升级为：

```text
法律文件 -> 清洗切分 -> embedding -> 向量库 / LlamaIndex / LangChain Retriever -> LegalRetrievalTool.retrieve()
```

对外接口仍然保持 `LegalMatch`，这样 `ReasoningAgent`、`JudgeAgent`、`ReviewAgent` 不需要重写。
