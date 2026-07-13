# 多案件回放测试集

本目录保留原有 `test_he.docx`、`test_li.docx` 和 `video_report.docx`，并新增五个按案件类型分类的可重复回放案例。

每个案例包含：

- `case.json`：案件类型、材料清单、权威核验及预期法条；
- `statements/`：当事人或证人笔录；
- `reports/`：监控、鉴定、检查、运营或扣押记录；
- 所有材料均为合成测试数据，不对应真实个人或案件。

运行全部案例：

```powershell
python -m case_agent_demo.case_replay --root 测试用例
```

回放结果用于检查证据抽取、Claim 聚合、主观证据融合、贝叶斯模型选择、法律 RAG 召回和终检意见，不代替人工法律判断。
