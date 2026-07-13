/* global cytoscape, lucide */

"use strict";

const KIND_META = {
  material: { label: "材料", color: "#56646c" },
  fact: { label: "事实", color: "#2f6fa3" },
  assertion: { label: "断言", color: "#a86f12" },
  claim: { label: "命题", color: "#167c5a" },
  derived_claim: { label: "派生命题", color: "#7254a3" },
  validation_issue: { label: "审查问题", color: "#b43a3a" },
};

const BAYES_META = {
  input: { label: "输入", color: "#2f6fa3" },
  intermediate: { label: "中间节点", color: "#a86f12" },
  derived: { label: "派生结果", color: "#167c5a" },
};

const RELATION_COLORS = {
  source_of: "#93a0a7",
  same_person: "#7e8d95",
  same_object: "#7e8d95",
  same_event: "#7e8d95",
  supports: "#167c5a",
  contradicts: "#b43a3a",
  needs_human_check: "#a86f12",
  asserts: "#a86f12",
  supports_claim: "#167c5a",
  opposes_claim: "#b43a3a",
  ambiguous_claim: "#8a9499",
  bayesian_input: "#7254a3",
  raises_issue: "#b43a3a",
};

const state = {
  snapshot: null,
  view: "evidence",
  cy: null,
  currentRun: null,
  scenarioOverrides: {},
  scenarioValues: {},
  selectedElementId: "",
};

const dom = {};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheDom();
  bindEvents();
  lucide.createIcons();
  try {
    const response = await fetch("/api/snapshot", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const snapshot = await response.json();
    applySnapshot(snapshot);
    setHealth("ready", "本地快照已载入");
  } catch (error) {
    setHealth("error", `快照载入失败：${error.message}`);
    showEmpty("无法读取快照", "本地服务未返回有效数据");
  }
}

function cacheDom() {
  [
    "caseType", "nodeCount", "runCount", "evidenceTab", "bayesianTab",
    "openSnapshot", "saveSnapshot", "snapshotFile", "evidenceControls",
    "bayesianControls", "kindFilters", "relationFilter", "toggleAllKinds",
    "runSelect", "runMeta", "scenarioControls", "resetScenario", "agentTrace",
    "graphSearch", "clearSearch", "zoomIn", "zoomOut", "fitGraph",
    "resetLayout", "graph", "emptyState", "emptyTitle", "emptyText", "legend",
    "detailKind", "detailTitle", "detailBody", "clearSelection", "healthDot",
    "healthText", "schemaVersion", "generatedAt",
  ].forEach((id) => { dom[id] = document.getElementById(id); });
}

function bindEvents() {
  document.querySelectorAll(".view-tab").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  dom.openSnapshot.addEventListener("click", () => dom.snapshotFile.click());
  dom.snapshotFile.addEventListener("change", openSnapshotFile);
  dom.saveSnapshot.addEventListener("click", downloadSnapshot);
  dom.runSelect.addEventListener("change", () => selectRun(dom.runSelect.value));
  dom.resetScenario.addEventListener("click", resetScenario);
  dom.relationFilter.addEventListener("change", applyEvidenceFilters);
  dom.toggleAllKinds.addEventListener("click", toggleAllKinds);
  dom.graphSearch.addEventListener("input", applySearch);
  dom.clearSearch.addEventListener("click", () => {
    dom.graphSearch.value = "";
    applySearch();
    dom.graphSearch.focus();
  });
  dom.zoomIn.addEventListener("click", () => zoomBy(1.2));
  dom.zoomOut.addEventListener("click", () => zoomBy(0.82));
  dom.fitGraph.addEventListener("click", fitGraph);
  dom.resetLayout.addEventListener("click", runLayout);
  dom.clearSelection.addEventListener("click", clearSelection);
}

function applySnapshot(snapshot) {
  validateSnapshot(snapshot);
  state.snapshot = snapshot;
  state.currentRun = null;
  state.scenarioOverrides = {};
  state.scenarioValues = {};
  state.selectedElementId = "";
  updateHeader();
  renderAgentTrace();
  populateRunSelect();
  renderKindFilters();
  renderRelationFilter();
  switchView(state.view, true);
}

function validateSnapshot(snapshot) {
  if (!snapshot || snapshot.schema_version !== "1.0") {
    throw new Error("不支持的快照版本");
  }
  if (!snapshot.evidence || !snapshot.bayesian) {
    throw new Error("快照缺少图谱数据");
  }
}

function updateHeader() {
  const meta = state.snapshot.meta || {};
  const evidence = state.snapshot.evidence || {};
  dom.caseType.textContent = meta.confirmed_case_type || "未标注案件类型";
  dom.nodeCount.textContent = String((evidence.nodes || []).length);
  dom.runCount.textContent = String((state.snapshot.bayesian.runs || []).length);
  dom.schemaVersion.textContent = state.snapshot.schema_version;
  dom.generatedAt.textContent = formatDate(state.snapshot.generated_at);
}

function renderAgentTrace() {
  dom.agentTrace.replaceChildren();
  const agents = state.snapshot.meta.executed_agents || [];
  agents.forEach((agent) => {
    const item = document.createElement("li");
    item.textContent = agent;
    dom.agentTrace.append(item);
  });
}

function switchView(view, force = false) {
  if (!force && state.view === view) return;
  state.view = view;
  document.querySelectorAll(".view-tab").forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  dom.evidenceControls.classList.toggle("is-hidden", view !== "evidence");
  dom.bayesianControls.classList.toggle("is-hidden", view !== "bayesian");
  dom.graphSearch.value = "";
  clearDetails();
  if (view === "evidence") {
    renderEvidenceGraph();
  } else {
    if (!state.currentRun) {
      const firstRun = state.snapshot.bayesian.runs?.[0];
      if (firstRun) selectRun(firstRun.id, false);
    }
    renderBayesianGraph();
  }
}

function renderEvidenceGraph() {
  const evidence = state.snapshot.evidence;
  if (!evidence.nodes.length) {
    destroyGraph();
    showEmpty("暂无证据图", "当前快照没有证据节点");
    return;
  }
  hideEmpty();
  const elements = [
    ...evidence.nodes.map((node) => ({ data: { ...node, type: "node" } })),
    ...evidence.edges.map((edge) => ({
      data: {
        ...edge,
        type: "edge",
        color: RELATION_COLORS[edge.relation] || "#8a9499",
      },
    })),
  ];
  createGraph(elements, evidenceStyles(), evidenceLayout());
  bindGraphSelection();
  applyEvidenceFilters();
  renderEvidenceLegend();
}

function renderBayesianGraph() {
  const run = state.currentRun;
  if (!run) {
    destroyGraph();
    showEmpty("暂无贝叶斯运行", "当前案件没有匹配并执行的模型");
    renderBayesianLegend();
    return;
  }
  hideEmpty();
  if (!Object.keys(state.scenarioValues).length) {
    recomputeScenario(false);
  }
  const elements = [
    ...run.nodes.map((node) => ({
      data: {
        id: `bn:${node.id}`,
        raw_id: node.id,
        label: node.label,
        role: node.role,
        node_type: node.type,
        observed: node.observed ? 1 : 0,
        value: state.scenarioValues[node.id] ?? node.value,
        captured_value: node.value,
        node,
      },
    })),
    ...run.edges.map((edge) => ({
      data: {
        id: `bn-edge:${edge.id}`,
        source: `bn:${edge.source}`,
        target: `bn:${edge.target}`,
        weight: edge.weight,
        weightLabel: formatSigned(edge.weight),
        edge,
      },
    })),
  ];
  createGraph(elements, bayesianStyles(), bayesianLayout());
  bindGraphSelection();
  renderBayesianLegend();
}

function createGraph(elements, style, layout) {
  destroyGraph();
  state.cy = cytoscape({
    container: dom.graph,
    elements,
    style,
    layout,
    minZoom: 0.18,
    maxZoom: 3.2,
    wheelSensitivity: 0.18,
    boxSelectionEnabled: false,
    selectionType: "single",
  });
  state.cy.on("tap", (event) => {
    if (event.target === state.cy) clearSelection();
  });
}

function destroyGraph() {
  if (state.cy) {
    state.cy.destroy();
    state.cy = null;
  }
}

function evidenceStyles() {
  return [
    {
      selector: "node",
      style: {
        "width": 68,
        "height": 48,
        "background-color": "#56646c",
        "border-width": 2,
        "border-color": "#ffffff",
        "label": "data(label)",
        "font-size": 9,
        "font-weight": 600,
        "color": "#263036",
        "text-wrap": "wrap",
        "text-max-width": 92,
        "text-valign": "bottom",
        "text-margin-y": 8,
        "overlay-opacity": 0,
      },
    },
    { selector: 'node[kind = "material"]', style: { "shape": "round-rectangle", "background-color": "#56646c", "width": 74, "height": 38 } },
    { selector: 'node[kind = "fact"]', style: { "shape": "ellipse", "background-color": "#2f6fa3" } },
    { selector: 'node[kind = "assertion"]', style: { "shape": "diamond", "background-color": "#a86f12", "width": 58, "height": 58 } },
    { selector: 'node[kind = "claim"]', style: { "shape": "round-rectangle", "background-color": "#167c5a", "width": 88, "height": 48 } },
    { selector: 'node[kind = "derived_claim"]', style: { "shape": "hexagon", "background-color": "#7254a3", "width": 82, "height": 60 } },
    { selector: 'node[kind = "validation_issue"]', style: { "shape": "tag", "background-color": "#b43a3a", "width": 72, "height": 44 } },
    {
      selector: "edge",
      style: {
        "width": 1.4,
        "line-color": "data(color)",
        "target-arrow-color": "data(color)",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.72,
        "curve-style": "bezier",
        "label": "data(label)",
        "font-size": 7,
        "color": "#66737a",
        "text-background-color": "#f7f9fa",
        "text-background-opacity": 0.88,
        "text-background-padding": 2,
        "overlay-opacity": 0,
      },
    },
    { selector: 'edge[relation = "contradicts"], edge[relation = "opposes_claim"]', style: { "line-style": "dashed", "width": 2.3 } },
    { selector: 'edge[relation = "same_person"], edge[relation = "same_object"], edge[relation = "same_event"]', style: { "target-arrow-shape": "none", "line-style": "dotted" } },
    { selector: "node:selected", style: { "border-color": "#f0b429", "border-width": 5 } },
    { selector: "edge:selected", style: { "width": 3.4, "line-color": "#f0b429", "target-arrow-color": "#f0b429" } },
    { selector: ".dim", style: { "opacity": 0.14, "text-opacity": 0.05 } },
    { selector: ".search-match", style: { "border-color": "#f0b429", "border-width": 6 } },
  ];
}

function bayesianStyles() {
  return [
    {
      selector: "node",
      style: {
        "width": 92,
        "height": 58,
        "shape": "round-rectangle",
        "background-color": "#a86f12",
        "border-width": 2,
        "border-color": "#ffffff",
        "label": (element) => `${element.data("label")}\n${formatPercent(element.data("value"))}`,
        "font-size": 9,
        "font-weight": 650,
        "color": "#263036",
        "text-wrap": "wrap",
        "text-max-width": 100,
        "text-valign": "bottom",
        "text-margin-y": 9,
        "overlay-opacity": 0,
      },
    },
    { selector: 'node[role = "input"]', style: { "background-color": "#2f6fa3" } },
    { selector: 'node[role = "intermediate"]', style: { "background-color": "#a86f12" } },
    { selector: 'node[role = "derived"]', style: { "background-color": "#167c5a", "shape": "hexagon", "width": 96, "height": 70 } },
    { selector: 'node[observed = 1]', style: { "border-color": "#182025", "border-style": "double", "border-width": 6 } },
    {
      selector: "edge",
      style: {
        "width": (element) => 1.2 + Math.min(2.8, Math.abs(element.data("weight"))),
        "line-color": (element) => element.data("weight") < 0 ? "#b43a3a" : "#6e7c83",
        "target-arrow-color": (element) => element.data("weight") < 0 ? "#b43a3a" : "#6e7c83",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.82,
        "curve-style": "bezier",
        "label": "data(weightLabel)",
        "font-size": 8,
        "color": "#4f5c62",
        "text-background-color": "#f7f9fa",
        "text-background-opacity": 0.9,
        "text-background-padding": 2,
        "overlay-opacity": 0,
      },
    },
    { selector: "node:selected", style: { "border-color": "#f0b429", "border-width": 6 } },
    { selector: "edge:selected", style: { "width": 4, "line-color": "#f0b429", "target-arrow-color": "#f0b429" } },
    { selector: ".scenario-changed", style: { "border-color": "#7254a3", "border-width": 6 } },
    { selector: ".dim", style: { "opacity": 0.14, "text-opacity": 0.05 } },
    { selector: ".search-match", style: { "border-color": "#f0b429", "border-width": 6 } },
  ];
}

function evidenceLayout() {
  return {
    name: "cose",
    animate: false,
    fit: true,
    padding: 72,
    nodeRepulsion: 7200,
    idealEdgeLength: 98,
    edgeElasticity: 110,
    gravity: 0.32,
    randomize: false,
  };
}

function bayesianLayout() {
  return {
    name: "breadthfirst",
    directed: true,
    fit: true,
    padding: 86,
    spacingFactor: 1.35,
    circle: false,
    grid: false,
    maximal: true,
  };
}

function bindGraphSelection() {
  state.cy.on("tap", "node", (event) => {
    const element = event.target;
    state.selectedElementId = element.id();
    highlightPath(element);
    if (state.view === "evidence") renderEvidenceNodeDetails(element.data());
    else renderBayesianNodeDetails(element.data());
  });
  state.cy.on("tap", "edge", (event) => {
    const element = event.target;
    state.selectedElementId = element.id();
    highlightPath(element);
    renderEdgeDetails(element);
  });
}

function highlightPath(element) {
  state.cy.elements().removeClass("dim");
  let related;
  if (element.isNode()) {
    related = state.view === "bayesian"
      ? element.union(element.predecessors()).union(element.successors())
      : element.closedNeighborhood();
  } else {
    related = element.union(element.connectedNodes());
  }
  state.cy.elements().not(related).addClass("dim");
}

function clearSelection() {
  state.selectedElementId = "";
  if (state.cy) {
    state.cy.elements().unselect();
    state.cy.elements().removeClass("dim");
  }
  clearDetails();
}

function clearDetails() {
  dom.detailKind.textContent = "未选择";
  dom.detailTitle.textContent = "节点详情";
  const placeholder = create("div", "detail-placeholder");
  const icon = document.createElement("i");
  icon.dataset.lucide = "mouse-pointer-2";
  const text = document.createElement("span");
  text.textContent = "选择节点或关系";
  placeholder.append(icon, text);
  dom.detailBody.replaceChildren(placeholder);
  lucide.createIcons();
}

function renderEvidenceNodeDetails(data) {
  dom.detailKind.textContent = KIND_META[data.kind]?.label || data.kind;
  dom.detailTitle.textContent = data.label;
  const fragment = document.createDocumentFragment();
  fragment.append(scoreStrip([
    ["类型", KIND_META[data.kind]?.label || data.kind],
    ["评分", formatPercent(data.score)],
    ["子类型", data.subkind || "-"],
  ]));

  const details = data.details || {};
  const core = pick(details, [
    "node_id", "assertion_id", "claim_id", "issue_id", "source_material_id",
    "person", "declarant", "actor", "predicate", "behavior_type", "target_person",
    "object", "event_id", "stance", "status", "severity", "reason", "required_action",
  ]);
  fragment.append(detailSection("核心字段", core));

  if (details.assessment) {
    fragment.append(detailSection("命题评估", pick(details.assessment, [
      "status", "support_index", "bayesian_posterior", "bayesian_model_version", "reasons",
    ])));
  }
  const relations = connectedSummary(data.id);
  if (relations.length) fragment.append(detailSection("相邻关系", { relations }));
  fragment.append(rawDetails(details));
  dom.detailBody.replaceChildren(fragment);
}

function renderBayesianNodeDetails(data) {
  const node = data.node;
  const current = state.scenarioValues[node.id] ?? node.value;
  const delta = current - node.value;
  dom.detailKind.textContent = `${BAYES_META[node.role]?.label || node.role} · ${node.type}`;
  dom.detailTitle.textContent = node.label;
  const fragment = document.createDocumentFragment();
  fragment.append(scoreStrip([
    ["运行值", formatPercent(node.value)],
    ["模拟值", formatPercent(current)],
    ["变化", formatSigned(delta)],
  ]));
  fragment.append(detailSection("节点状态", {
    node_id: node.id,
    role: node.role,
    type: node.type,
    observed: node.observed,
    anchor_input: node.is_anchor,
    source_claim_ids: node.source_claim_ids,
    parents: node.parents,
  }));

  const calculation = calculateNode(node.id, state.currentRun, state.scenarioValues);
  fragment.append(formulaSection(calculation));
  if (calculation.terms?.length) fragment.append(contributionSection(calculation.terms));
  fragment.append(detailSection("参数", node.parameters || {}));
  fragment.append(rawDetails({ ...node, scenario_value: current, calculation }));
  dom.detailBody.replaceChildren(fragment);
}

function renderEdgeDetails(element) {
  const data = element.data();
  const source = element.source().data("label") || element.source().data("raw_id");
  const target = element.target().data("label") || element.target().data("raw_id");
  const relation = data.relation || "Bayesian dependency";
  dom.detailKind.textContent = "关系";
  dom.detailTitle.textContent = relation;
  const fragment = document.createDocumentFragment();
  fragment.append(detailSection("连接", {
    source,
    target,
    relation,
    weight: data.weight,
  }));
  fragment.append(rawDetails(data.details || data.edge || data));
  dom.detailBody.replaceChildren(fragment);
}

function connectedSummary(nodeId) {
  if (!state.cy) return [];
  const node = state.cy.getElementById(nodeId);
  if (!node.length) return [];
  return node.connectedEdges().map((edge) => {
    const other = edge.source().id() === nodeId ? edge.target() : edge.source();
    return `${edge.data("relation")} → ${other.data("label") || other.data("raw_id")}`;
  });
}

function detailSection(title, values) {
  const section = create("section", "detail-section");
  const heading = document.createElement("h3");
  heading.textContent = title;
  const list = create("dl", "detail-list");
  const entries = Object.entries(values || {}).filter(([, value]) => hasValue(value));
  if (!entries.length) {
    const dt = document.createElement("dt");
    dt.textContent = "状态";
    const dd = document.createElement("dd");
    dd.textContent = "无数据";
    list.append(dt, dd);
  } else {
    entries.forEach(([key, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = key;
      const dd = document.createElement("dd");
      dd.textContent = formatValue(value);
      list.append(dt, dd);
    });
  }
  section.append(heading, list);
  return section;
}

function formulaSection(calculation) {
  const section = create("section", "detail-section");
  const heading = document.createElement("h3");
  heading.textContent = "计算";
  const block = create("div", "formula-block");
  const lines = [calculation.formula || "-"];
  if (calculation.intercept !== undefined) lines.push(`intercept = ${formatNumber(calculation.intercept)}`);
  if (calculation.raw_score !== undefined) lines.push(`raw = ${formatNumber(calculation.raw_score)}`);
  if (calculation.prior !== undefined) lines.push(`prior = ${formatNumber(calculation.prior)}`);
  if (calculation.leak !== undefined) lines.push(`leak = ${formatNumber(calculation.leak)}`);
  block.textContent = lines.join("\n");
  section.append(heading, block);
  return section;
}

function contributionSection(terms) {
  const section = create("section", "detail-section");
  const heading = document.createElement("h3");
  heading.textContent = "父节点贡献";
  const list = create("div", "contribution-list");
  const max = Math.max(0.001, ...terms.map((term) => Math.abs(term.contribution ?? (term.weight * term.value))));
  terms.forEach((term) => {
    const row = create("div", "contribution-row");
    const name = document.createElement("code");
    name.textContent = term.parent;
    const value = document.createElement("span");
    value.textContent = formatNumber(term.value);
    const contribution = document.createElement("span");
    const contributionValue = term.contribution ?? (term.weight * term.value);
    contribution.textContent = formatSigned(contributionValue);
    const bar = create("div", "contribution-bar");
    const fill = document.createElement("span");
    fill.style.width = `${Math.min(100, Math.abs(contributionValue) / max * 100)}%`;
    if (contributionValue < 0) fill.style.backgroundColor = "#b43a3a";
    bar.append(fill);
    row.append(name, value, contribution, bar);
    list.append(row);
  });
  section.append(heading, list);
  return section;
}

function rawDetails(value) {
  const details = create("details", "raw-details");
  const summary = document.createElement("summary");
  summary.textContent = "原始快照";
  const pre = create("pre", "raw-json");
  pre.textContent = JSON.stringify(value, null, 2);
  details.append(summary, pre);
  return details;
}

function scoreStrip(items) {
  const strip = create("div", "score-strip");
  items.forEach(([label, value]) => {
    const cell = create("div", "score-cell");
    const caption = document.createElement("span");
    caption.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = String(value ?? "-");
    cell.append(caption, strong);
    strip.append(cell);
  });
  return strip;
}

function renderKindFilters() {
  dom.kindFilters.replaceChildren();
  const counts = state.snapshot.evidence.counts?.by_kind || {};
  Object.entries(counts).forEach(([kind, count]) => {
    const label = create("label", "filter-item");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.dataset.kind = kind;
    checkbox.addEventListener("change", applyEvidenceFilters);
    const swatch = create("span", "filter-swatch");
    swatch.style.backgroundColor = KIND_META[kind]?.color || "#8a9499";
    const name = document.createElement("span");
    name.textContent = KIND_META[kind]?.label || kind;
    const countSpan = create("span", "filter-count");
    countSpan.textContent = count;
    label.append(checkbox, swatch, name, countSpan);
    dom.kindFilters.append(label);
  });
}

function renderRelationFilter() {
  const relations = [...new Set(state.snapshot.evidence.edges.map((edge) => edge.relation))].sort();
  dom.relationFilter.replaceChildren();
  const all = document.createElement("option");
  all.value = "all";
  all.textContent = "全部关系";
  dom.relationFilter.append(all);
  relations.forEach((relation) => {
    const option = document.createElement("option");
    option.value = relation;
    option.textContent = relation;
    dom.relationFilter.append(option);
  });
}

function applyEvidenceFilters() {
  if (!state.cy || state.view !== "evidence") return;
  const enabled = new Set(
    [...dom.kindFilters.querySelectorAll("input:checked")].map((input) => input.dataset.kind)
  );
  state.cy.nodes().forEach((node) => {
    node.style("display", enabled.has(node.data("kind")) ? "element" : "none");
  });
  const relation = dom.relationFilter.value;
  state.cy.edges().forEach((edge) => {
    const endpointsVisible = edge.source().style("display") !== "none" && edge.target().style("display") !== "none";
    const relationVisible = relation === "all" || edge.data("relation") === relation;
    edge.style("display", endpointsVisible && relationVisible ? "element" : "none");
  });
}

function toggleAllKinds() {
  const inputs = [...dom.kindFilters.querySelectorAll("input")];
  const next = !inputs.every((input) => input.checked);
  inputs.forEach((input) => { input.checked = next; });
  applyEvidenceFilters();
}

function populateRunSelect() {
  dom.runSelect.replaceChildren();
  const runs = state.snapshot.bayesian.runs || [];
  if (!runs.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "无运行";
    dom.runSelect.append(option);
    dom.runSelect.disabled = true;
    state.currentRun = null;
    renderRunMeta();
    renderScenarioControls();
    return;
  }
  dom.runSelect.disabled = false;
  runs.forEach((run) => {
    const option = document.createElement("option");
    option.value = run.id;
    option.textContent = run.label;
    dom.runSelect.append(option);
  });
  state.currentRun = runs[0];
  dom.runSelect.value = runs[0].id;
  resetScenario(false);
}

function selectRun(runId, rerender = true) {
  const run = state.snapshot.bayesian.runs.find((item) => item.id === runId);
  if (!run) return;
  state.currentRun = run;
  dom.runSelect.value = run.id;
  resetScenario(false);
  if (rerender && state.view === "bayesian") renderBayesianGraph();
}

function resetScenario(rerender = true) {
  const run = state.currentRun;
  state.scenarioOverrides = {};
  if (run) {
    run.nodes.filter((node) => node.role === "input").forEach((node) => {
      state.scenarioOverrides[node.id] = Number(node.value);
    });
  }
  recomputeScenario(false);
  renderRunMeta();
  renderScenarioControls();
  if (rerender && state.view === "bayesian") renderBayesianGraph();
}

function renderRunMeta() {
  dom.runMeta.replaceChildren();
  const run = state.currentRun;
  if (!run) return;
  [
    ["模型", `${run.model_id}:${run.version}`],
    ["校准", run.calibration_status],
    ["分组", run.group_key],
    ["锚点", run.anchor_claim_id],
  ].forEach(([label, value]) => {
    const item = create("div", "run-meta-item");
    const caption = document.createElement("span");
    caption.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value || "-";
    strong.title = value || "-";
    item.append(caption, strong);
    dom.runMeta.append(item);
  });
}

function renderScenarioControls() {
  dom.scenarioControls.replaceChildren();
  const run = state.currentRun;
  if (!run) return;
  run.nodes.filter((node) => node.role === "input").forEach((node) => {
    const control = create("div", "slider-control");
    const label = document.createElement("label");
    label.htmlFor = `slider-${safeDomId(node.id)}`;
    label.textContent = node.label;
    label.title = node.id;
    const row = create("div", "slider-value-row");
    const input = document.createElement("input");
    input.id = `slider-${safeDomId(node.id)}`;
    input.type = "range";
    input.min = "0";
    input.max = "1";
    input.step = "0.01";
    input.value = String(state.scenarioOverrides[node.id] ?? node.value);
    const value = create("span", "slider-value");
    value.textContent = Number(input.value).toFixed(2);
    input.addEventListener("input", () => {
      state.scenarioOverrides[node.id] = Number(input.value);
      value.textContent = Number(input.value).toFixed(2);
      recomputeScenario(true);
    });
    row.append(input, value);
    const source = create("span", "slider-source");
    source.textContent = node.source_claim_ids.length
      ? `${node.source_claim_ids.length} 个 Claim 来源`
      : "模型先验输入";
    control.append(label, row, source);
    dom.scenarioControls.append(control);
  });
}

function recomputeScenario(updateGraph = true) {
  const run = state.currentRun;
  if (!run) {
    state.scenarioValues = {};
    return;
  }
  const specs = run.spec.nodes || [];
  const values = {};
  const pending = [...specs];
  let guard = pending.length + 2;
  while (pending.length && guard > 0) {
    guard -= 1;
    let progressed = false;
    for (let index = pending.length - 1; index >= 0; index -= 1) {
      const node = pending[index];
      const parents = node.parents || [];
      if (!parents.every((parent) => Object.hasOwn(values, parent))) continue;
      if (Object.hasOwn(state.scenarioOverrides, node.id)) {
        values[node.id] = clamp01(state.scenarioOverrides[node.id]);
      } else if (node.type === "prior") {
        values[node.id] = clamp01(Number(node.prior));
      } else if (node.type === "logistic") {
        const raw = Number(node.intercept) + parents.reduce(
          (sum, parent) => sum + Number(node.weights[parent]) * values[parent], 0
        );
        values[node.id] = sigmoid(raw);
      } else if (node.type === "noisy_or") {
        let missed = 1 - Number(node.leak || 0);
        parents.forEach((parent) => {
          missed *= 1 - Number(node.weights[parent]) * values[parent];
        });
        values[node.id] = clamp01(1 - missed);
      }
      pending.splice(index, 1);
      progressed = true;
    }
    if (!progressed) break;
  }
  run.nodes.forEach((node) => {
    if (!Object.hasOwn(values, node.id)) values[node.id] = Number(node.value);
  });
  state.scenarioValues = values;
  if (updateGraph && state.cy && state.view === "bayesian") {
    state.cy.batch(() => {
      run.nodes.forEach((node) => {
        const element = state.cy.getElementById(`bn:${node.id}`);
        if (!element.length) return;
        const current = values[node.id];
        element.data("value", current);
        element.toggleClass("scenario-changed", Math.abs(current - node.value) > 0.0001);
      });
    });
    if (state.selectedElementId.startsWith("bn:")) {
      const selected = state.cy.getElementById(state.selectedElementId);
      if (selected.length && selected.isNode()) renderBayesianNodeDetails(selected.data());
    }
  }
}

function calculateNode(nodeId, run, values) {
  const spec = (run.spec.nodes || []).find((node) => node.id === nodeId) || {};
  if (Object.hasOwn(state.scenarioOverrides, nodeId)) {
    return { formula: "soft evidence override", prior: state.scenarioOverrides[nodeId], terms: [] };
  }
  if (spec.type === "prior") return { formula: "prior", prior: spec.prior, terms: [] };
  const parents = spec.parents || [];
  const terms = parents.map((parent) => ({
    parent,
    value: Number(values[parent] || 0),
    weight: Number(spec.weights?.[parent] || 0),
    contribution: Number(values[parent] || 0) * Number(spec.weights?.[parent] || 0),
  }));
  if (spec.type === "logistic") {
    const raw = Number(spec.intercept || 0) + terms.reduce((sum, term) => sum + term.contribution, 0);
    return {
      formula: "sigmoid(intercept + Σ weight × parent)",
      intercept: Number(spec.intercept || 0),
      raw_score: raw,
      result: sigmoid(raw),
      terms,
    };
  }
  if (spec.type === "noisy_or") {
    return {
      formula: "1 - (1 - leak) × Π(1 - weight × parent)",
      leak: Number(spec.leak || 0),
      result: values[nodeId],
      terms,
    };
  }
  return { formula: "unknown", terms };
}

function applySearch() {
  if (!state.cy) return;
  const query = dom.graphSearch.value.trim().toLocaleLowerCase();
  state.cy.elements().removeClass("search-match");
  if (!query) return;
  const matches = state.cy.nodes().filter((node) => {
    const text = `${node.data("label") || ""} ${node.data("raw_id") || ""}`.toLocaleLowerCase();
    return text.includes(query);
  });
  matches.addClass("search-match");
  if (matches.length) state.cy.animate({ fit: { eles: matches, padding: 90 }, duration: 250 });
}

function zoomBy(factor) {
  if (!state.cy) return;
  const center = { x: dom.graph.clientWidth / 2, y: dom.graph.clientHeight / 2 };
  state.cy.zoom({ level: state.cy.zoom() * factor, renderedPosition: center });
}

function fitGraph() {
  if (state.cy) state.cy.animate({ fit: { eles: state.cy.elements(":visible"), padding: 65 }, duration: 220 });
}

function runLayout() {
  if (!state.cy) return;
  state.cy.layout(state.view === "evidence" ? evidenceLayout() : bayesianLayout()).run();
}

function renderEvidenceLegend() {
  renderLegend(Object.entries(KIND_META).map(([, meta]) => meta));
}

function renderBayesianLegend() {
  renderLegend(Object.entries(BAYES_META).map(([, meta]) => meta));
}

function renderLegend(items) {
  dom.legend.replaceChildren();
  items.forEach((item) => {
    const row = create("div", "legend-item");
    const swatch = create("span", "legend-swatch");
    swatch.style.backgroundColor = item.color;
    const label = document.createElement("span");
    label.textContent = item.label;
    row.append(swatch, label);
    dom.legend.append(row);
  });
}

async function openSnapshotFile() {
  const [file] = dom.snapshotFile.files;
  if (!file) return;
  try {
    const snapshot = JSON.parse(await file.text());
    applySnapshot(snapshot);
    setHealth("ready", `本地文件：${file.name}`);
  } catch (error) {
    setHealth("error", `文件无效：${error.message}`);
  } finally {
    dom.snapshotFile.value = "";
  }
}

function downloadSnapshot() {
  if (!state.snapshot) return;
  const blob = new Blob([JSON.stringify(state.snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `reasoning-${new Date().toISOString().replace(/[:.]/g, "-")}.snapshot.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function setHealth(status, text) {
  dom.healthDot.classList.toggle("is-ready", status === "ready");
  dom.healthDot.classList.toggle("is-error", status === "error");
  dom.healthText.textContent = text;
}

function showEmpty(title, text) {
  dom.emptyTitle.textContent = title;
  dom.emptyText.textContent = text;
  dom.emptyState.classList.remove("is-hidden");
}

function hideEmpty() {
  dom.emptyState.classList.add("is-hidden");
}

function create(tag, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  return element;
}

function pick(object, keys) {
  return Object.fromEntries(keys.filter((key) => hasValue(object?.[key])).map((key) => [key, object[key]]));
}

function hasValue(value) {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function formatValue(value) {
  if (Array.isArray(value)) return value.map((item) => formatValue(item)).join("；");
  if (typeof value === "object" && value !== null) return JSON.stringify(value, null, 2);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(1)}%`;
}

function formatSigned(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number >= 0 ? "+" : ""}${formatNumber(number)}`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || "-");
  return date.toLocaleString("zh-CN", { hour12: false });
}

function safeDomId(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]/g, "-");
}

function clamp01(value) {
  return Math.min(1, Math.max(0, Number(value)));
}

function sigmoid(value) {
  return value >= 0
    ? 1 / (1 + Math.exp(-value))
    : Math.exp(value) / (1 + Math.exp(value));
}
