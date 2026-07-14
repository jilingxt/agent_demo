# v0.58 十案验收摘要

- 随机种子：`58`
- 案例总数：`10`
- 确定性通过：`10`
- 确定性失败：`0`
- Git 修订：`df2b39575d5eb9b416d3c11c05486daf061c4b7f`

| 案例 | 法律条文 | 复杂情形 | 结果 | 贝叶斯组件/弃权 |
|---|---|---|---|---|
| CR-185 | 中华人民共和国刑法第一百八十五条 | business_authorization_dispute | passed | status_duty |
| CR-186 | 中华人民共和国刑法第一百八十六条 | partial_admission | passed | status_duty |
| CR-189 | 中华人民共和国刑法第一百八十九条 | evidence_insufficient | passed | status_duty |
| CR-353 | 中华人民共和国刑法第三百五十三条 | direct_denial | passed | 安全弃权 |
| CR-429 | 中华人民共和国刑法第四百二十九条 | non_offense_context | passed | 安全弃权 |
| PS-31 | 中华人民共和国治安管理处罚法第三十一条 | ordinary_activity_dispute | passed | public_order |
| PS-50 | 中华人民共和国治安管理处罚法第五十条 | actor_attribution_dispute | passed | 安全弃权 |
| PS-51 | 中华人民共和国治安管理处罚法第五十一条 | full_admission | passed | conduct_result |
| PS-52 | 中华人民共和国治安管理处罚法第五十二条 | alternative_explanation | passed | 安全弃权 |
| PS-83 | 中华人民共和国治安管理处罚法第八十三条 | statutory_exception | passed | 安全弃权 |

> 贝叶斯派生值是版本化专家参数下的证据关系支持值，不是事实概率、有罪概率或处罚概率。
