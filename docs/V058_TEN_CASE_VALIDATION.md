# v0.58 十案验证说明

## 1. 目的

v0.58 用十个跨领域复杂合成案例验证当前通用证据推理结构，而不是新增十个案件专用分支。验证重点是：Agent 能否输出结构化事实，Claim 是否正确区分支持、反对和未知，贝叶斯 Tool 是否只在有锚点时运行，法律 RAG 是否给出可追溯候选，FinalConflictAgent 是否指出证据缺口和边界。

贝叶斯派生值是版本化专家参数下的关系支持值，**不是事实概率**、有罪概率或处罚概率。

## 2. 抽样方法

- 数据源：本项目法律索引中的《中华人民共和国刑法》和《中华人民共和国治安管理处罚法》；
- 随机种子：`58`；
- 两部法律分别抽取五条；
- 纯处罚衔接条文不适合作为独立事实案例时，记录拒绝原因和替换轨迹；
- 抽样结果保存在 `测试用例/v058随机条文/sampling_manifest.json`。

## 3. 最终样本

| 编号 | 法律条文 | 场景 | 预期复杂性 |
|---|---|---|---|
| CR-353 | 刑法第三百五十三条 | 引诱行为争议 | 指认与替代解释并存 |
| CR-185 | 刑法第一百八十五条 | 资金授权争议 | 有流水、授权记录缺失 |
| CR-189 | 刑法第一百八十九条 | 票据证据不足 | 行为痕迹存在、关键结果未证实 |
| CR-429 | 刑法第四百二十九条 | 训练救助争议 | 身份、职责和不作为关系不完整 |
| CR-186 | 刑法第一百八十六条 | 贷款部分承认 | 审批行为承认、关联关系存在争议 |
| PS-51 | 治安管理处罚法第五十一条 | 行为完整承认 | 多来源承认与独立结果材料 |
| PS-52 | 治安管理处罚法第五十二条 | 行为与医疗解释 | 行为和结果有记录、因果解释需收窄 |
| PS-31 | 治安管理处罚法第三十一条 | 普通活动纠纷 | 事实存在但不支持违法组织性质 |
| PS-50 | 治安管理处罚法第五十条 | 账号归属争议 | 账号痕迹存在、具体操作者不足 |
| PS-83 | 治安管理处罚法第八十三条 | 主动清除例外 | 基础事实与法定例外并列呈现 |

## 4. 每案材料结构

```text
case.json                         案例、法条和材料清单
sampling.json                     抽样来源和原文哈希
statements/*.docx                 合成笔录
reports/*.docx                    合成研判、资金、业务或检查报告
report_images/*.png               可视报告页（部分案例）
expected/semantic_assertions.json 黄金结构化事实
expected/expected_outcome.json    Claim、模型、法条和审查预期
```

所有文件均标注“合成测试材料，仅用于系统验证，不对应真实人员、单位或案件”。

## 5. 两类验收互不替代

### 5.1 确定性黄金回放

`tests/test_v058_case_acceptance.py` 用固定 Assertion 驱动现有生产链，验证工程逻辑。该层是发布硬门禁，不受大模型温度和措辞波动影响。

### 5.2 真实 Agent 对比

`scripts/run_v058_live_agent_acceptance.py` 调用当前模型读取 DOCX/PNG，保存原始返回和字段级差异。真实模型测试不会使用关键词兜底，也不会接触黄金答案。它用于发现 prompt、开放谓词和事件对齐问题，不用于掩盖下游逻辑错误。

## 6. v0.58 通用修复

- 贝叶斯组件需要真实锚点谓词，辅助谓词不能单独触发；
- `legal_query_terms` 只帮助检索，不作为事实支持；
- `element_role` 只表达通用的行为人归属或法律要素缺口；
- 证据融合保留来源组去重和反向证据；
- RAG 不再因前 50 个中文候选截断漏掉相关治安条文；
- DOCX 回放使用统一提取器，旧材料只从保留目录读取；
- 未能完成结构化语义时保留 `unresolved_observation`，不恢复关键词兜底。

## 7. 运行命令

```powershell
E:\miniconda\python.exe -m pytest -p no:cacheprovider tests\test_v058_case_acceptance.py -q
E:\miniconda\python.exe scripts\run_v058_live_agent_acceptance.py --corpus "测试用例\v058随机条文" --output artifacts\v058-live-agent
E:\miniconda\python.exe scripts\build_v058_acceptance_report.py --corpus "测试用例\v058随机条文" --output artifacts\v058-acceptance --verify
```

## 8. 结果判读

- `supported/strongly_supported`：现有独立来源形成支持，仍不等于最终认定；
- `contested_but_not_refuted`：正向仍占优但存在直接反向材料，应补充调查；
- `insufficient_evidence/unassessed`：输入不足或无法评估；
- `opposing_evidence_dominant`：反向材料占优，需要人工复核；
- `abstentions`：贝叶斯组件缺少锚点或必要输入，系统主动不算；
- 法律条文：仅为可追溯候选，不能反向证明案件事实或直接决定处罚。

## 9. 发布边界

十案证明的是当前抽象结构能处理多种证据形态和安全失败路径，不表示项目已经覆盖全部违法犯罪类型。遇到未注册的事实关系时，项目仍可形成 EvidenceGraph、EvidenceClaim、法律候选和审查清单；贝叶斯部分应安全弃权，待稳定关系、可解释输入和可校准参数具备后再发布新组件。
