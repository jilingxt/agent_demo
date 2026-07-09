# agent_demo 严格重构执行方案（Codex 执行版）

> 目标：将当前 `agent_demo` 从“多 Agent Pipeline Demo”升级为“EvidenceGraph + EvidenceClaim + ConfidenceEngine + LegalKnowledgeBase/RAG + FinalConflictAgent”的案件证据分析工作流。
>
> 本文档用于交给 Codex 严格执行。请按阶段小步提交，不要一次性大重构。

---

## 0. 总体原则

### 0.1 不要一次性重写项目

本项目已有可运行 demo。所有改造必须遵守：

1. 保持旧接口兼容。
2. 每个阶段必须能运行测试。
3. 不要删除旧类，除非已有兼容 alias 或 wrapper。
4. 不要让 `ReasoningAgent` 直接读取全部原始材料。
5. 不要把 RAG 整体升格为 Agent。
6. 不要引入多 Agent 群聊式协作框架。
7. 不要输出最终定罪、处罚、责任承担等裁判式结论。
8. 所有新增核心数据结构必须有单元测试。
9. 所有文件删除、证据删除、法律文件删除默认软删除。
10. 所有检索结果必须可追溯到 `source/document/chunk/node/edge/claim`。

### 0.2 Tool 与 Agent 的边界

请按以下原则重构：

```text
Tool = 确定性、可复用、可缓存、可测试的能力
Agent = 需要 LLM 做语义理解、判断、推理、审查的能力
```

RAG 本体不是 Agent。RAG 是知识库工具。只有以下环节可以可选使用 Agent：

```text
LegalDocumentUnderstandingAgent  # 入库时识别法律文件类型、条款结构、领域
LegalQueryBuilderAgent           # 根据 EvidenceGraph 生成检索 query
```

---

## 1. 当前架构问题总结

当前项目主要问题：

1. `agents.py` 过大，混合了：
   - PlanningAgent
   - TextAgent
   - PicAgent
   - ReportImageAgent
   - EvidenceGraphAgent
   - ConflictAgent
   - ReasoningAgent
   - JudgeAgent
   - ReviewAgent
   - 大量规则 fallback 函数

2. workflow 当前仍是：

   ```text
   收集所有 facts -> 最后一次性 EvidenceGraphAgent.build(facts)
   ```

   不是增量入图。

3. 当前 `confidence` 混合了：
   - 模型抽取质量
   - 材料来源可靠性
   - 事实真实性
   - 多源互证程度

4. 当前法律检索仍是静态 JSONL：

   ```text
   LegalRetrievalTool -> legal_library/laws.jsonl
   ```

   不是真正 RAG。

5. 当前 `JudgeAgent` / `ReviewAgent` / `ConflictAgent` 职责分散，后续应合并为 `FinalConflictAgent` 的最终审查链。

---

## 2. 最终目标架构

最终目标结构：

```text
case_agent_demo/
  domain/
    models.py
    enums.py

  evidence/
    intake.py
    repository.py
    material_plan.py

  graph/
    graph_store.py
    relation_rules.py
    claim_builder.py
    confidence_engine.py
    graph_query.py

  rag/
    legal_kb.py
    document_loader.py
    chunker.py
    embeddings.py
    vector_store.py
    keyword_index.py
    domain_affinity.py
    legal_query_builder.py

  agents/
    planning_agent.py
    text_evidence_agent.py
    image_understanding_agent.py
    report_understanding_agent.py
    relation_agent.py
    reasoning_agent.py
    final_conflict_agent.py

  tools/
    image_recognition_tool.py
    pre_conflict_detector_tool.py

  workflow.py
  cli.py
```

但是不要第一步就大搬目录。第一阶段允许先在根目录新增文件，后续再目录化。

第一阶段建议结构：

```text
case_agent_demo/
  models.py
  workflow.py
  agents.py
  evidence_repository.py
  graph_store.py
  relation_tools.py
  confidence.py
  legal_kb.py
  domain_affinity.py
  final_conflict_agent.py
```

---

## 3. 执行阶段总览

请按以下 PR / commit 顺序执行：

```text
PR 1: Refactor core models and preserve compatibility
PR 2: Implement incremental EvidenceGraph workflow
PR 3: Implement EvidenceClaim and ConfidenceEngine
PR 4: Implement LegalKnowledgeBaseTool with CRUD and keyword retrieval
PR 5: Add domain affinity and hybrid RAG ranking
PR 6: Implement FinalConflictAgent and challenge/supplementary investigation flow
PR 7: Optional module split and cleanup
```

每个 PR 必须：

- 添加或更新测试；
- 保持旧测试通过；
- 不破坏 CLI；
- 不删除旧 public API；
- 更新必要文档。

---

# PR 1：核心模型整理与兼容层

## 1.1 目标

增强 `models.py`，为后续 EvidenceGraph、EvidenceClaim、RAG、置信度打基础。

不要删除当前：

```python
Fact
CaseGraph
EvidenceGraph
LegalMatch
Challenge
ReviewResult
WorkflowResult
```

## 1.2 修改 `models.py`

### 1.2.1 新增常量

可先用字符串，不强制 Enum。建议新增：

```python
NODE_TYPE_FACT = "fact"
NODE_TYPE_MATERIAL = "material"
NODE_TYPE_REPORT_OPINION = "report_opinion"

EDGE_TYPE_SOURCE_OF = "source_of"
EDGE_TYPE_SAME_PERSON = "same_person"
EDGE_TYPE_SAME_OBJECT = "same_object"
EDGE_TYPE_SAME_EVENT = "same_event"
EDGE_TYPE_SUPPORTS = "supports"
EDGE_TYPE_CONTRADICTS = "contradicts"
EDGE_TYPE_NEEDS_HUMAN_CHECK = "needs_human_check"
```

### 1.2.2 扩展 `EvidenceNode`

当前已有 `EvidenceNode`，请扩展字段：

```python
@dataclass(frozen=True)
class EvidenceNode:
    node_id: str
    node_type: str
    source_material_id: str
    source_type: str
    summary: str

    person: str = ""
    behavior: str = ""
    time: str = ""
    location: str = ""
    object: str = ""

    # extraction confidence only
    confidence: float = 0.8

    # new fields
    polarity: str = "affirm"          # affirm / deny / uncertain
    claim_type: str = ""              # violence / injury_consequence / property_damage / taking_property / presence / general
    source_party: str = ""            # suspect / victim / witness / official / unknown
    observation_type: str = ""        # statement / image_observation / report_opinion / document_text
    status: str = "active"            # active / archived / deleted
    version: int = 1

    raw_ref: str = ""
    human_confirmed: bool = False
    metadata: dict = field(default_factory=dict)
```

### 1.2.3 扩展 `EvidenceEdge`

```python
@dataclass(frozen=True)
class EvidenceEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    reason: str
    confidence: float = 0.8
    evidence_basis: list[str] = field(default_factory=list)

    status: str = "active"
    version: int = 1
    metadata: dict = field(default_factory=dict)
```

### 1.2.4 新增 `ConfidenceProfile`

```python
@dataclass(frozen=True)
class ConfidenceProfile:
    extraction_quality: float = 0.0
    source_reliability: float = 0.0
    corroboration_score: float = 0.0
    contradiction_score: float = 0.0
    independence_score: float = 0.0
    uncertainty: float = 0.0
    final_score: float = 0.0
    label: str = ""
    reasons: list[str] = field(default_factory=list)
```

### 1.2.5 新增 `EvidenceClaim`

```python
@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    subject: str
    behavior_type: str
    object: str = ""
    time_bucket: str = ""
    location: str = ""

    supporting_node_ids: list[str] = field(default_factory=list)
    opposing_node_ids: list[str] = field(default_factory=list)
    related_edge_ids: list[str] = field(default_factory=list)

    confidence_profile: ConfidenceProfile | None = None

    status: str = "active"
    metadata: dict = field(default_factory=dict)
```

### 1.2.6 扩展 `CaseGraph`

当前 `CaseGraph` 有：

```python
facts
nodes
edges
```

新增：

```python
claims: list[EvidenceClaim] = field(default_factory=list)
```

保持 `facts/nodes` 互转兼容逻辑。

### 1.2.7 更新 `fact_to_node`

`fact_to_node()` 需要补充：

```python
polarity = infer_polarity(fact.behavior)
claim_type = infer_claim_type(fact.behavior, fact.object)
observation_type = fact.source_type
```

要求：

- 如果 behavior 包含 `没有/未/否认/不承认/没`，`polarity = deny`
- 否则 `polarity = affirm`
- 如果包含 `疑似/可能/不确定/无法确认`，`polarity = uncertain`

claim_type 基础规则：

```text
打架/动手/殴打/伤害/抱摔/推搡/掐脖子 -> violence
轻伤/重伤/骨折/伤情/鉴定意见 -> injury_consequence
损坏/毁坏/砸坏/摔坏 -> property_damage
拿走/窃取/盗窃/非法占有 -> taking_property
现场/出现/在场/不在 -> presence
其他 -> general
```

## 1.3 测试

新增或更新：

```text
tests/test_models_confidence_claims.py
```

测试点：

1. `fact_to_node` 能识别 `polarity=deny`
2. `fact_to_node` 能识别 `claim_type`
3. `CaseGraph(facts=[...])` 能自动生成 nodes
4. `CaseGraph(nodes=[...])` 能兼容生成 facts
5. `EvidenceClaim` 可创建
6. `ConfidenceProfile` 可创建

---

# PR 2：增量 EvidenceGraph Workflow

## 2.1 目标

将 workflow 从：

```text
先收集 facts -> 最后一次性 build graph
```

改为：

```text
每处理一份材料 -> 生成节点 -> 立刻入图 -> 立刻建边
```

## 2.2 扩展 `GraphStoreTool`

当前 `GraphStoreTool` 只有基础 upsert/list/to_graph。扩展为：

```python
class GraphStoreTool:
    def add_node(self, node: EvidenceNode) -> EvidenceNode: ...
    def update_node(self, node_id: str, patch: dict) -> EvidenceNode: ...
    def delete_node(self, node_id: str, soft_delete: bool = True) -> None: ...
    def get_node(self, node_id: str) -> EvidenceNode | None: ...
    def list_nodes(self, filters: dict | None = None) -> list[EvidenceNode]: ...

    def add_edge(self, edge: EvidenceEdge) -> EvidenceEdge: ...
    def update_edge(self, edge_id: str, patch: dict) -> EvidenceEdge: ...
    def delete_edge(self, edge_id: str, soft_delete: bool = True) -> None: ...
    def get_edge(self, edge_id: str) -> EvidenceEdge | None: ...
    def list_edges(self, filters: dict | None = None) -> list[EvidenceEdge]: ...

    def neighbors(self, node_id: str, edge_type: str | None = None) -> list[EvidenceNode]: ...
    def find_edges_between(self, left_id: str, right_id: str) -> list[EvidenceEdge]: ...

    def to_graph(self) -> EvidenceGraph: ...
```

Keep old `upsert_node` and `upsert_edge` as aliases:

```python
upsert_node = add_node
upsert_edge = add_edge
```

## 2.3 修改 `EvidenceGraphAgent`

新增方法：

```python
class EvidenceGraphAgent:
    def add_fact(self, store: GraphStoreTool, fact: Fact) -> EvidenceNode:
        ...
```

逻辑：

1. 生成 material node
2. 生成 fact node
3. 添加 `source_of` edge
4. 查已有 fact nodes
5. 调用 `RelationRuleTool` 生成关系边
6. 写入 graph store

保持旧方法：

```python
def build(self, facts: list[Fact]) -> CaseGraph:
    store = GraphStoreTool()
    for fact in facts:
        self.add_fact(store, fact)
    return store.to_graph()
```

## 2.4 修改 workflow

将当前：

```python
facts: list[Fact] = []
...
facts.extend(...)
...
case_graph = self.evidence_graph_agent.build(facts)
```

改为：

```python
graph_store = GraphStoreTool()
facts: list[Fact] = []

def ingest_facts(new_facts: list[Fact]) -> None:
    facts.extend(new_facts)
    for fact in new_facts:
        self.evidence_graph_agent.add_fact(graph_store, fact)
```

每个 Agent 返回 facts 后调用：

```python
ingest_facts(new_facts)
```

最终：

```python
case_graph = graph_store.to_graph()
```

要求：

- `WorkflowResult.case_graph.facts` 仍可用
- `WorkflowResult.case_graph.nodes` 有值
- `WorkflowResult.case_graph.edges` 有值
- `executed_agents` 仍包含旧名字

## 2.5 测试

新增：

```text
tests/test_workflow_incremental_graph.py
```

测试点：

1. workflow 运行后有 nodes
2. workflow 运行后有 source_of edges
3. 同一人/同一对象材料能产生 relation edges
4. `case_graph.facts` 兼容旧测试
5. `executed_agents` 不丢失

---

# PR 3：EvidenceClaim + ConfidenceEngine

## 3.1 目标

将“置信度”从单个 Fact/Node 的模型自信，升级为 claim 级的证据互证强度。

核心原则：

```text
EvidenceNode.confidence = 抽取质量 / OCR质量 / 识别质量
EvidenceClaim.confidence_profile.final_score = 事实命题综合可信度
```

## 3.2 新增文件

```text
case_agent_demo/confidence.py
```

## 3.3 新增 `ClaimBuilder`

```python
class ClaimBuilder:
    def build_claims(self, graph: EvidenceGraph) -> list[EvidenceClaim]:
        ...

    def update_claims_for_new_node(
        self,
        graph: EvidenceGraph,
        new_node: EvidenceNode,
        existing_claims: list[EvidenceClaim],
    ) -> list[EvidenceClaim]:
        ...
```

第一版可简单实现：

- 根据 `person + claim_type + object + location/time弱归一化` 聚合为 claim
- polarity = affirm 的节点进入 `supporting_node_ids`
- polarity = deny 的节点进入 `opposing_node_ids`
- `contradicts` edge 关联到 `related_edge_ids`
- `supports` edge 关联到 `related_edge_ids`

claim_id 格式：

```text
CL-{claim_type}-{safe_subject}-{safe_object}
```

## 3.4 新增 `ConfidenceEngine`

```python
class ConfidenceEngine:
    def score_claim(self, claim: EvidenceClaim, graph: EvidenceGraph) -> ConfidenceProfile:
        ...

    def score_claims(self, graph: EvidenceGraph) -> list[EvidenceClaim]:
        ...
```

## 3.5 来源权重

第一版使用规则表：

```python
SOURCE_RELIABILITY = {
    "statement": 0.52,
    "evidence_image": 0.55,
    "report_image": 0.68,
    "official_report": 0.75,
    "forensic_report": 0.78,
    "party_submitted_image": 0.45,
    "manual_verified": 0.85,
}
```

如果 node.metadata 或 source_party 标记：

```text
suspect -> 0.45
victim -> 0.52
witness -> 0.58
official -> 0.75
unknown -> 0.50
```

## 3.6 多源互证计算

实现饱和函数，避免多个证人无限抬高置信度：

```python
def saturated_sum(weights: list[float]) -> float:
    return 1 - math.exp(-sum(max(0.0, w) for w in weights))
```

## 3.7 否认回答的惩罚

否认回答不得直接归零事实。

计算：

```python
support_strength = saturated_sum(support_weights)
opposition_strength = saturated_sum(opposition_weights)

score = sigmoid(
    logit(0.45)
    + 1.5 * support_strength
    - 1.2 * opposition_strength
    - 0.8 * uncertainty
)
```

实现 helper：

```python
def sigmoid(x: float) -> float: ...
def logit(p: float) -> float: ...
```

## 3.8 争议区间

label 规则：

```python
if score >= 0.85 and opposition_strength < 0.25:
    label = "多源较强印证"
elif score >= 0.70:
    label = "有一定印证"
elif score >= 0.50:
    label = "争议事实，尚不足以否定"
elif score >= 0.35:
    label = "明显存疑，需补强"
else:
    label = "低可信或被冲突削弱"
```

`0.50 <= score < 0.70` 是反方质证区间。

## 3.9 uncertainty 规则

第一版可简单实现：

```text
低置信节点存在 -> +0.15
只有单一支持节点 -> +0.20
存在 opposing nodes -> +0.20
来源未知 -> +0.10
只有当事人材料，无独立来源 -> +0.20
```

上限 clamp 到 1.0。

## 3.10 输出 reasons

每个 ConfidenceProfile 必须生成 reasons，例如：

```text
- 被 2 个节点支持
- 存在 1 个相反否认节点
- 支持来源包含 report_image
- 缺少独立证人或监控材料
- 进入争议事实区间，建议补强
```

## 3.11 workflow 接入

在 workflow 中：

```python
claims = self.claim_builder.build_claims(case_graph)
scored_claims = self.confidence_engine.score_claims(case_graph_with_claims)
case_graph = CaseGraph(..., claims=scored_claims)
```

第一版可以在所有节点建完后统一构建 claims。后续再做增量 claim update。

## 3.12 测试

新增：

```text
tests/test_confidence_engine.py
```

测试点：

1. 单一 statement 支持 -> label 为单源或弱印证 / 有一定印证以下
2. statement + report 支持 -> score 上升
3. 支持 + 对方否认 -> score 下降但不归零
4. score 在 0.50~0.70 时 label 为“争议事实，尚不足以否定”
5. 低置信图片节点提高 uncertainty
6. reasons 不为空

---

# PR 4：LegalKnowledgeBaseTool + 文档 CRUD + 关键词检索

## 4.1 目标

用真正的 `LegalKnowledgeBaseTool` 替代静态 JSONL-only 思路，但保留旧 `LegalRetrievalTool.retrieve(payload)` 兼容。

第一版先实现：

```text
txt/md/jsonl 入库
chunk
metadata/chunk 存储
keyword search
soft delete
reindex
retrieve_for_case
retrieve_for_review
```

不要第一版就强依赖 FAISS/Chroma。

## 4.2 新增目录

```text
legal_knowledge/
  incoming/
  active/
  archived/
  metadata/
  index/
```

代码中如果目录不存在，应自动创建。

## 4.3 新增文件

```text
case_agent_demo/legal_kb.py
```

## 4.4 新增模型

可放在 `models.py` 或 `legal_kb.py`，建议先放 `models.py`：

```python
@dataclass(frozen=True)
class LegalDocument:
    document_id: str
    title: str
    doc_type: str
    source_path: str
    source: str = ""
    version: str = "v1"
    document_hash: str = ""
    effective_status: str = "effective"  # effective / archived / deleted
    domain_affinities: list[DomainAffinity] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LegalChunk:
    chunk_id: str
    document_id: str
    text: str
    title: str
    article: str = ""
    clause: str = ""
    doc_type: str = ""
    keywords: list[str] = field(default_factory=list)
    legal_elements: list[str] = field(default_factory=list)
    domain_affinities: list[DomainAffinity] = field(default_factory=list)
    score: float = 0.0
    effective_status: str = "effective"
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LegalRAGResult:
    matches: list[LegalMatch]
    chunks: list[LegalChunk]
    query: str
    purpose: str
    cache_hit: bool = False
    query_trace: dict = field(default_factory=dict)
```

如果 `DomainAffinity` 尚未实现，PR 4 可以先定义占位版本，PR 5 再完善。

## 4.5 `LegalKnowledgeBaseTool` API

```python
class LegalKnowledgeBaseTool:
    def __init__(self, root: str | Path = "legal_knowledge") -> None:
        ...

    def ingest_folder(self, folder: str | Path | None = None) -> list[LegalDocument]:
        ...

    def ingest_document(
        self,
        file_path: str | Path,
        doc_type: str | None = None,
        metadata: dict | None = None,
    ) -> LegalDocument:
        ...

    def update_document(
        self,
        document_id: str,
        new_file_path: str | Path,
        metadata: dict | None = None,
    ) -> LegalDocument:
        ...

    def delete_document(self, document_id: str, soft_delete: bool = True) -> None:
        ...

    def reindex(self, document_id: str | None = None) -> None:
        ...

    def search(
        self,
        query: str,
        purpose: str = "legal_basis",
        doc_types: list[str] | None = None,
        domain_ids: list[str] | None = None,
        top_k: int = 8,
    ) -> LegalRAGResult:
        ...

    def retrieve_for_case(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        top_k: int = 8,
    ) -> LegalRAGResult:
        ...

    def retrieve_for_review(
        self,
        case_type: str,
        evidence_graph: EvidenceGraph,
        draft_report: str = "",
        top_k: int = 12,
    ) -> LegalRAGResult:
        ...
```

## 4.6 存储格式

第一版用 JSONL：

```text
legal_knowledge/index/documents.jsonl
legal_knowledge/index/chunks.jsonl
```

每次 ingest/update/delete/reindex 后写回。

## 4.7 文本加载

支持：

```text
.txt
.md
.jsonl
```

jsonl 兼容旧 `legal_library/laws.jsonl` 格式。

如果输入是旧 `laws.jsonl`，每一行转为一个 `LegalChunk`。

## 4.8 chunk 策略

优先按条文切。

识别模式：

```text
第X条
第X章
第X节
```

如果不能识别，则按段落合并，每 chunk 控制在 500~1200 中文字符。

## 4.9 keyword search

第一版不需要 SQLite FTS，可以先简单实现：

```python
score = keyword_hits + title_hits + article_hits + doc_type_bonus
```

搜索 query 拆词：

- 中文先用简单关键词包含
- 不强制引入 jieba
- 可选后续支持 jieba

## 4.10 LegalMatch 兼容

`LegalRAGResult.matches` 必须返回旧 `LegalMatch`：

```python
LegalMatch(
    law_id=chunk.chunk_id,
    law_name=chunk.title,
    article=chunk.article,
    legal_element="；".join(chunk.legal_elements) or chunk.text,
    matched_behavior=query,
    source=f"legal_kb:{purpose}:{chunk.document_id}:{chunk.chunk_id}",
    effective_status=chunk.effective_status,
)
```

## 4.11 修改 `LegalRetrievalTool`

保留旧类：

```python
class LegalRetrievalTool:
    def retrieve(self, payload: dict[str, Any]) -> list[LegalMatch]:
        ...
```

内部优先调用 `LegalKnowledgeBaseTool`：

```python
result = self.legal_kb.retrieve_for_case(...)
return result.matches
```

如果 `legal_knowledge` 没有内容，则 fallback 到旧 `legal_library/laws.jsonl`。

## 4.12 测试

新增：

```text
tests/test_legal_knowledge_base.py
```

测试点：

1. 自动创建 legal_knowledge 目录
2. ingest txt
3. ingest md
4. ingest old laws.jsonl
5. search 能返回 chunks
6. retrieve_for_case 能返回 LegalRAGResult
7. delete_document soft delete 后默认不返回
8. update_document 旧版本 archived，新版本 effective
9. LegalRetrievalTool.retrieve 兼容旧输出 list[LegalMatch]

---

# PR 5：Domain Affinity + Hybrid RAG Ranking

## 5.1 目标

添加“法律/条例与领域相关度”的索引层，让检索可以先按领域定位法律/条例，再找条款。

## 5.2 新增模型

```python
@dataclass(frozen=True)
class LegalDomain:
    domain_id: str
    name: str
    parent_id: str = ""
    aliases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class DomainAffinity:
    domain_id: str
    score: float
    source: str = "auto"  # manual / keyword / semantic / feedback
    reason: str = ""
```

## 5.3 默认领域表

新增文件：

```text
case_agent_demo/domain_affinity.py
```

定义：

```python
DEFAULT_LEGAL_DOMAINS = [
    LegalDomain("criminal_injury", "故意伤害领域", keywords=[...]),
    LegalDomain("property_damage", "故意毁坏财物领域", keywords=[...]),
    LegalDomain("theft", "盗窃领域", keywords=[...]),
    LegalDomain("public_security_punishment", "治安处罚领域", keywords=[...]),
    LegalDomain("procedure_compliance", "办案程序规范领域", keywords=[...]),
    LegalDomain("evidence_review", "证据审查领域", keywords=[...]),
    LegalDomain("forensic_injury", "伤情鉴定领域", keywords=[...]),
    LegalDomain("image_video_evidence", "图片/监控/视听资料领域", keywords=[...]),
    LegalDomain("identification", "辨认领域", keywords=[...]),
    LegalDomain("statement_review", "询问笔录/证人证言审查领域", keywords=[...]),
    LegalDomain("supplementary_investigation", "补充侦查/补证领域", keywords=[...]),
    LegalDomain("report_boundary", "报告边界/禁止最终判断领域", keywords=[...]),
]
```

关键词示例：

```python
"criminal_injury": ["故意伤害", "殴打", "轻伤", "重伤", "伤情", "他人身体"]
"procedure_compliance": ["程序", "告知", "询问", "扣押", "调取", "送达", "办案"]
"evidence_review": ["证据", "证明", "真实性", "关联性", "合法性", "审查"]
"forensic_injury": ["鉴定", "伤情", "轻伤二级", "人体损伤", "鉴定意见"]
```

## 5.4 `DomainAffinityIndexer`

```python
class DomainAffinityIndexer:
    def score_text(self, text: str, manual_affinities: dict[str, float] | None = None) -> list[DomainAffinity]:
        ...

    def score_document(self, document: LegalDocument, chunks: list[LegalChunk]) -> list[DomainAffinity]:
        ...

    def score_chunk(self, chunk: LegalChunk) -> list[DomainAffinity]:
        ...
```

第一版计算：

```python
if manual_score exists:
    final = 0.60 * manual_score + 0.40 * keyword_score
else:
    final = keyword_score
```

后续有 embedding 后扩展：

```python
final = 0.50 * manual + 0.25 * keyword + 0.25 * semantic
```

## 5.5 `CaseDomainRouter`

```python
class CaseDomainRouter:
    def infer_domains(self, case_type: str, evidence_graph: EvidenceGraph) -> list[DomainAffinity]:
        ...
```

规则：

- case_type 包含 故意伤害：
  - criminal_injury 0.90
  - forensic_injury 0.75
  - evidence_review 0.65
- graph 中出现 轻伤/重伤/骨折/鉴定：
  - forensic_injury >= 0.85
- graph 中出现 监控/图片/照片/视频：
  - image_video_evidence >= 0.75
- graph 中存在 contradicts/opposing claims：
  - evidence_review >= 0.70
  - supplementary_investigation >= 0.60
- graph 中出现 辨认：
  - identification >= 0.75

## 5.6 LegalKnowledgeBaseTool search ranking

修改 search：

```python
final_score = (
    0.40 * keyword_score
    + 0.25 * domain_affinity_score
    + 0.20 * doc_type_score
    + 0.15 * article_title_score
)
```

如果未来有 vector_score：

```python
final_score = (
    0.40 * vector_score
    + 0.20 * keyword_score
    + 0.25 * domain_affinity_score
    + 0.10 * doc_type_score
    + 0.05 * status_score
)
```

## 5.7 `retrieve_for_review` 特殊规则

`retrieve_for_review()` 应优先领域：

```text
procedure_compliance
evidence_review
forensic_injury
image_video_evidence
statement_review
identification
supplementary_investigation
report_boundary
```

## 5.8 测试

新增：

```text
tests/test_domain_affinity.py
tests/test_legal_kb_domain_retrieval.py
```

测试点：

1. 包含“故意伤害/轻伤”的 chunk 命中 criminal_injury 和 forensic_injury
2. 包含“询问/辨认/调取”的 chunk 命中 procedure_compliance
3. retrieve_for_case 优先返回领域相关条款
4. retrieve_for_review 优先返回证据/程序/鉴定相关规范
5. domain score 参与最终排序

---

# PR 6：FinalConflictAgent + 质证与补充侦查建议

## 6.1 目标

将当前 `ConflictAgent/JudgeAgent/ReviewAgent` 的职责升级为最终审查链：

```text
PreConflictDetectorTool = 规则冲突检测
FinalConflictAgent = 证据冲突 + 置信度 + RAG规范审查 + 报告边界 + 补充侦查建议
```

## 6.2 新增模型

```python
@dataclass(frozen=True)
class ValidationIssue:
    issue_id: str
    issue_type: str
    severity: str
    target_node_ids: list[str] = field(default_factory=list)
    target_edge_ids: list[str] = field(default_factory=list)
    target_claim_ids: list[str] = field(default_factory=list)
    reason: str = ""
    required_action: str = ""
    supporting_law_ids: list[str] = field(default_factory=list)
    supporting_chunk_ids: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

`issue_type` 支持：

```text
evidence_conflict
evidence_insufficiency
contested_but_not_refuted
procedure_risk
legal_basis_missing
report_overclaim
forensic_review_needed
image_evidence_low_confidence
human_confirmation_required
```

## 6.3 新增 FinalConflictAgent

新增文件：

```text
case_agent_demo/final_conflict_agent.py
```

或放入 agents 后续拆分。

```python
class FinalConflictAgent:
    def review(
        self,
        confirmed_case_type: str,
        evidence_graph: EvidenceGraph,
        draft_report: str,
        legal_rag_result: LegalRAGResult,
    ) -> list[ValidationIssue]:
        ...
```

## 6.4 审查逻辑

### 6.4.1 高冲突边

如果 graph.edges 中有 `contradicts`：

- 生成 `evidence_conflict`
- severity 根据 claim confidence 和 edge confidence 判定

### 6.4.2 争议事实未被否定

如果 claim 的 label 是：

```text
争议事实，尚不足以否定
```

生成：

```python
issue_type = "contested_but_not_refuted"
severity = "medium"
```

required_action 根据 claim_type 自动生成。

### 6.4.3 明显存疑

如果 claim label 是：

```text
明显存疑，需补强
低可信或被冲突削弱
```

生成：

```python
issue_type = "evidence_insufficiency"
severity = "high"
```

### 6.4.4 法律依据缺失

如果 `legal_rag_result.matches` 为空，或没有 chunks：

```python
issue_type = "legal_basis_missing"
severity = "high"
```

### 6.4.5 报告越界

如果 draft_report 包含：

```text
已经构成犯罪
应当处罚
必然构成
依法应当追究
```

生成：

```python
issue_type = "report_overclaim"
severity = "high"
```

### 6.4.6 低置信图片

如果 node.source_type 是 image 相关且 confidence < 0.75：

```python
issue_type = "image_evidence_low_confidence"
severity = "medium"
```

## 6.5 补充侦查建议表

新增：

```python
SUPPLEMENTARY_INVESTIGATION_ACTIONS = {
    "violence": [
        "补充调取现场监控或周边监控",
        "询问现场在场人员或独立证人",
        "核对伤情形成时间与行为因果关系",
        "核对就医记录、伤情照片、鉴定意见依据",
    ],
    "property_damage": [
        "补充固定损坏物品照片、维修记录或价格认定材料",
        "核对物品权属和损坏前后状态",
        "询问在场人员确认损坏经过",
    ],
    "taking_property": [
        "补充调取监控或电子轨迹",
        "核对物品权属、去向和占有状态",
        "询问物品保管人或现场人员",
    ],
    "presence": [
        "核对监控、门禁、定位或考勤记录",
        "询问同场人员",
        "核对时间线是否闭合",
    ],
    "injury_consequence": [
        "核对鉴定意见所依据的病历、影像资料和检查记录",
        "审查伤情形成机制与陈述行为是否一致",
    ],
    "general": [
        "补充核对原始材料来源",
        "补充询问相关人员",
        "核对时间、地点、对象和证据来源",
    ],
}
```

## 6.6 workflow 接入

第一阶段不要删除 JudgeAgent/ReviewAgent，先并行加入 FinalConflictAgent：

```python
legal_rag_result = self.legal_kb.retrieve_for_review(...)
validation_issues = self.final_conflict_agent.review(...)

final_report = self.reasoning_agent.revise_with_validation_issues(
    draft_report,
    validation_issues,
)
```

如果不想立即改 ReasoningAgent，先将 `ValidationIssue` 转成 `Challenge` 兼容：

```python
Challenge(
    challenge_type=issue.issue_type,
    target=",".join(issue.target_claim_ids or issue.target_node_ids),
    reason=f"{issue.reason} 建议：{issue.required_action}",
    severity=issue.severity,
)
```

## 6.7 测试

新增：

```text
tests/test_final_conflict_agent.py
```

测试点：

1. contested claim 生成 contested_but_not_refuted
2. low score claim 生成 evidence_insufficiency
3. report overclaim 生成 report_overclaim
4. missing legal rag 生成 legal_basis_missing
5. low confidence image node 生成 image_evidence_low_confidence
6. required_action 不为空
7. issue 能转换为 Challenge 兼容旧 ReasoningAgent.revise

---

# PR 7：可选模块拆分与清理

## 7.1 目标

在前 6 个 PR 测试稳定后，再拆目录。不要提前做。

## 7.2 拆分建议

`case_agent_demo/agents.py` 拆为：

```text
case_agent_demo/agents/planning_agent.py
case_agent_demo/agents/text_evidence_agent.py
case_agent_demo/agents/image_understanding_agent.py
case_agent_demo/agents/report_understanding_agent.py
case_agent_demo/agents/reasoning_agent.py
case_agent_demo/agents/final_conflict_agent.py
```

`case_agent_demo/tools.py` 拆为：

```text
case_agent_demo/tools/legal_retrieval_legacy.py
case_agent_demo/tools/image_recognition_tool.py
case_agent_demo/tools/pre_conflict_detector_tool.py
```

新增：

```text
case_agent_demo/rag/
case_agent_demo/graph/
case_agent_demo/evidence/
```

## 7.3 兼容

`case_agent_demo/agents.py` 可以保留并 re-export：

```python
from case_agent_demo.agents.text_evidence_agent import TextAgent
...
```

---

# 8. 工作流最终形态

最终 workflow 应该接近：

```text
EvidenceRepository.load_materials()
  ↓
MaterialPlanTool.plan()
  ↓
PlanningAgent.suggest_case_type()
  ↓
人工确认 case_type
  ↓
并行处理材料
  ├── TextAgent(statement) -> Fact/EvidenceNode
  ├── ImageRecognitionTool(image) -> ImageObservation
  │       └── ImageUnderstandingAgent -> Fact/EvidenceNode
  ├── ImageRecognitionTool(report_image) -> ImageObservation
  │       └── ReportUnderstandingAgent -> Fact/EvidenceNode
  └── DocumentTextExtractionTool(docx/pdf/txt) -> ReportUnderstandingAgent -> Fact/EvidenceNode
  ↓
每生成一个节点：
  ├── GraphStoreTool.add_node()
  ├── RelationRuleTool.add_edges()
  └── later: ClaimBuilder incremental update
  ↓
ClaimBuilder.build_claims()
  ↓
ConfidenceEngine.score_claims()
  ↓
PreConflictDetectorTool.detect()
  ↓
LegalKnowledgeBaseTool.retrieve_for_case()
  ↓
ReasoningAgent 生成初稿
  ↓
LegalKnowledgeBaseTool.retrieve_for_review()
  ↓
FinalConflictAgent.review()
  ↓
ReasoningAgent 根据 ValidationIssue/Challenge 修订
  ↓
Review compatibility check
  ↓
输出最终辅助分析报告
```

---

# 9. 禁止事项

Codex 不得执行以下操作：

1. 不得删除 `Fact`。
2. 不得删除 `LegalRetrievalTool.retrieve(payload)`。
3. 不得删除 `RagLegalAgent` legacy wrapper。
4. 不得让 ReasoningAgent 直接读取全部原始材料。
5. 不得硬删除证据材料和法律文件。
6. 不得让 RAG 作为自由对话 Agent。
7. 不得引入 CrewAI/AutoGen 等多 Agent 群聊框架。
8. 不得把图片 OCR、图片理解、报告理解全部塞进一个大 Agent。
9. 不得输出“已经构成犯罪/应当处罚/必然构成”等最终裁判式结论。
10. 不得在代码或文档中写入真实 API key。
11. 不得提交真实涉案材料。
12. 不得在第一阶段强依赖重型外部服务，如 Milvus/Qdrant/Postgres；应先用本地 JSONL/可替换接口。

---

# 10. 测试总清单

最终应至少包含：

```text
tests/test_models_confidence_claims.py
tests/test_workflow_incremental_graph.py
tests/test_graph_store_crud.py
tests/test_relation_rule_tool.py
tests/test_confidence_engine.py
tests/test_legal_knowledge_base.py
tests/test_domain_affinity.py
tests/test_legal_kb_domain_retrieval.py
tests/test_final_conflict_agent.py
tests/test_legacy_legal_retrieval_compat.py
```

---

# 11. 验收标准

## 11.1 EvidenceGraph

- workflow 运行后存在 nodes
- workflow 运行后存在 edges
- 每个 fact node 有 source_of edge
- 相同人员、对象、事件能产生关联边
- 否认事实与肯定事实能产生 contradicts edge
- 低置信图片能产生 needs_human_check edge

## 11.2 EvidenceClaim / Confidence

- claim 能聚合支持和反对节点
- 多源支持能提高 claim confidence
- 双方否认能降低 claim confidence 但不直接归零
- 争议区间能被识别
- reasons 能解释分数来源
- FinalConflictAgent 能基于争议区间提出补充侦查建议

## 11.3 LegalKnowledgeBase / RAG

- 能从 `legal_knowledge/incoming` 入库 txt/md/jsonl
- 能生成 documents/chunks
- 能搜索 chunks
- 能软删除 document
- 能 update document 并归档旧版本
- 能 retrieve_for_case
- 能 retrieve_for_review
- 返回结果可追溯 document_id/chunk_id/source

## 11.4 Domain Affinity

- 法律/条例能被标注领域相关度
- chunk 能有领域相关度
- 检索能按领域优先
- review 检索能优先证据/程序/鉴定/补充侦查领域

## 11.5 FinalConflictAgent

- 能发现 evidence_conflict
- 能发现 contested_but_not_refuted
- 能发现 evidence_insufficiency
- 能发现 legal_basis_missing
- 能发现 report_overclaim
- 能发现 image_evidence_low_confidence
- issue 必须带 required_action

## 11.6 Backward Compatibility

- 原 CLI 可运行
- 旧 tests 尽量不需要大改
- `WorkflowResult.legal_matches` 仍存在
- `WorkflowResult.conflicts` 仍存在
- `WorkflowResult.challenges` 仍存在
- `WorkflowResult.review` 仍存在

---

# 12. 建议 commit 命名

```text
refactor: add claim and confidence models
refactor: support incremental evidence graph updates
feat: add claim builder and confidence engine
feat: add legal knowledge base with document CRUD
feat: add legal domain affinity ranking
feat: add final conflict review agent
test: add coverage for graph confidence and legal kb
docs: update architecture for evidence graph and legal rag
```

---

# 13. 最终目标描述

完成后，项目应变为：

> 一个基于 EvidenceGraph、EvidenceClaim、ConfidenceEngine 和 LegalKnowledgeBase 的案件证据分析工作流。  
> 系统能增量读取证据材料，抽取事实节点，建立证据关系边，聚合事实命题并计算可解释置信度。  
> 双方否认不会直接否定事实，但会作为反证降低 claim confidence；当事实进入“争议但不足以否定”区间时，FinalConflictAgent 会提出反方质证和补充侦查建议。  
> 法律与规范性文件不再依赖静态 JSONL，而是通过 LegalKnowledgeBaseTool 入库、切分、索引、检索，并通过领域相关度优先定位相关法律/条例。  
> ReasoningAgent 只基于结构化证据图、claim 置信度、RAG 检索结果和 FinalConflictAgent 审查意见输出辅助分析报告，不作最终裁判式结论。
