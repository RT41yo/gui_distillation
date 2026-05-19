from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


def _load_agent_map(app: str, maps_dir: Path) -> dict[str, Any]:
    path = maps_dir / app / "agent_map.json"

    if not path.exists():
        raise FileNotFoundError(
            f"agent_map.json not found: {path}. "
            f"Run: python -m ui_explorer.cli.build_agent_map --app {app}"
        )

    return json.loads(path.read_text(encoding="utf-8"))


def _safe_json_for_script(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _item_label(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    description = str(item.get("description") or "").strip()
    role = str(item.get("role") or "").strip()

    if name and description:
        return f"{name} — {description}"
    if name:
        return name
    if description:
        return description
    return role or "item"


def _state_label(state: dict[str, Any]) -> str:
    label = str(state.get("label") or "").strip()
    state_id = str(state.get("state_id") or "")
    depth = state.get("depth")

    if label:
        return f"{label}\\n{state_id}\\ndepth={depth}"

    return f"{state_id}\\ndepth={depth}"


def _build_visual_data(
    agent_map: dict[str, Any],
    *,
    max_items_per_state: int,
) -> dict[str, Any]:
    states_raw = agent_map.get("states", {})
    items_raw = agent_map.get("items", {})

    states: list[dict[str, Any]] = []
    state_edges: list[dict[str, Any]] = []
    item_edges: list[dict[str, Any]] = []
    scoped_item_edges: list[dict[str, Any]] = []
    delta_item_edges: list[dict[str, Any]] = []
    item_ids_used: set[str] = set()

    def add_item_edge(
        collection: list[dict[str, Any]],
        *,
        edge_id: str,
        source: str,
        ref_item: dict[str, Any],
        edge_type: str,
    ) -> None:
        ref = ref_item.get("ref")
        if not ref:
            return

        full_item = items_raw.get(ref)
        if not full_item:
            return

        item_ids_used.add(ref)
        collection.append({
            "id": edge_id,
            "source": source,
            "target": ref,
            "type": edge_type,
            "label": _item_label(full_item),
            "role": full_item.get("role", ""),
            "description": full_item.get("description", ""),
        })

    for state_id, state in states_raw.items():
        verified_actions = state.get("verified_actions", [])
        incoming_actions = state.get("incoming_actions", [])
        observed_items = state.get("observed_items", [])
        scoped_observed_items = state.get("scoped_observed_items", [])
        delta_observed_items = state.get("delta_observed_items", [])
        state_capabilities = state.get("state_capabilities", [])

        scoped_observed_items = state.get("scoped_observed_items", [])
        state_capabilities = state.get("state_capabilities", [])

        states.append({
            "id": state_id,
            "type": "state",
            "label": _state_label(state),
            "short_label": state.get("label") or state_id,
            "depth": state.get("depth", 0),
            "active_root": state.get("active_root", {}),

            "verified_count": len(verified_actions),
            "incoming_count": len(incoming_actions),
            "observed_count": len(observed_items),
            "delta_count": len(delta_observed_items),
            "scoped_count": len(scoped_observed_items),
            "capabilities_count": len(state_capabilities),

            "incoming_actions": incoming_actions,
            "primary_incoming_action": state.get("primary_incoming_action"),

            "scoped_observed_items": scoped_observed_items,
            "scoped_observed_source": state.get("scoped_observed_source"),
            "scoped_observed_confidence": state.get("scoped_observed_confidence"),

            "state_capabilities": state_capabilities,
            "state_capabilities_source": state.get("state_capabilities_source"),
            "state_capabilities_scoped_source": state.get("state_capabilities_scoped_source"),
            "state_capabilities_scoped_confidence": state.get("state_capabilities_scoped_confidence"),

            "delta_base_state": state.get("delta_base_state"),
        })

        for action in verified_actions:
            to_state = action.get("to_state")
            if not to_state or to_state not in states_raw:
                continue

            state_edges.append({
                "id": action.get("edge_id"),
                "source": state_id,
                "target": to_state,
                "type": "verified_action",
                "label": action.get("name") or action.get("role") or "action",
                "role": action.get("role", ""),
                "description": action.get("description", ""),
                "edge_status": action.get("edge_status", ""),
                "method": action.get("method", ""),
                "has_bbox": "bbox" in action,
            })

        for ref_item in observed_items[:max_items_per_state]:
            add_item_edge(
                item_edges,
                edge_id=f"{state_id}->observed->{ref_item.get('ref')}",
                source=state_id,
                ref_item=ref_item,
                edge_type="observes",
            )

        for ref_item in scoped_observed_items[:max_items_per_state]:
            add_item_edge(
                scoped_item_edges,
                edge_id=f"{state_id}->scoped->{ref_item.get('ref')}",
                source=state_id,
                ref_item=ref_item,
                edge_type="scoped_observes",
            )

        for ref_item in delta_observed_items:
            add_item_edge(
                delta_item_edges,
                edge_id=f"{state_id}->delta->{ref_item.get('ref')}",
                source=state_id,
                ref_item=ref_item,
                edge_type="delta_observes",
            )

    items: list[dict[str, Any]] = []

    for item_id in sorted(item_ids_used):
        item = items_raw[item_id]

        items.append({
            "id": item_id,
            "type": "item",
            "label": _item_label(item),
            "short_label": _item_label(item),
            "role": item.get("role", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "status": item.get("status", ""),
            "states": item.get("states", []),
            "parent_path_tail": item.get("parent_path_tail", []),
            "has_visible_bbox_hint": "visible_bbox_hint" in item,
        })

    return {
        "schema_version": agent_map.get("schema_version"),
        "app_id": agent_map.get("app_id"),
        "root_state_id": agent_map.get("root_state_id"),
        "summary": agent_map.get("summary", {}),
        "states": states,
        "items": items,
        "state_edges": state_edges,
        "item_edges": item_edges,
        "scoped_item_edges": scoped_item_edges,
        "delta_item_edges": delta_item_edges,
        "max_items_per_state": max_items_per_state,
    }


def _html_document(data: dict[str, Any]) -> str:
    title = f"Agent Map — {data.get('app_id')}"
    data_json = _safe_json_for_script(data)

    template = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #0f172a;
    --panel: #111827;
    --panel2: #1f2937;
    --text: #e5e7eb;
    --muted: #9ca3af;
    --line: #334155;
    --state: #60a5fa;
    --item: #a78bfa;
    --action: #34d399;
    --observe: #fbbf24;
    --scoped: #38bdf8;
    --delta: #fb7185;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
  }
  header {
    padding: 14px 18px;
    border-bottom: 1px solid var(--line);
    display: flex;
    gap: 14px;
    align-items: center;
    flex-wrap: wrap;
    background: #020617;
  }
  header h1 { margin: 0; font-size: 18px; font-weight: 650; }
  header .meta { color: var(--muted); font-size: 13px; }
  .layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(460px, 36vw);
    height: calc(100vh - 62px);
  }
  .main {
    position: relative;
    overflow: auto;
    min-width: 0;
    min-height: 0;
  }
  .toolbar {
    position: absolute;
    z-index: 5;
    left: 14px;
    top: 14px;
    right: 14px;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 10px;
    backdrop-filter: blur(8px);
  }
  .toolbar input[type="text"] {
    min-width: 260px;
    flex: 1;
    background: var(--panel);
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 8px 10px;
  }
  .toolbar label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--muted);
  }
  .toolbar input[type="range"] { width: 120px; }
  button {
    background: var(--panel2);
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 8px 10px;
    cursor: pointer;
  }
  button:hover { background: #374151; }
  svg {
    width: 100%;
    height: 100%;
    min-width: 100%;
    min-height: 100%;
    display: block;
  }
  .edge {
    stroke: var(--line);
    stroke-width: 1.4;
    opacity: 0.58;
    fill: none;
    cursor: pointer;
  }
  .edge.action { stroke: var(--action); marker-end: url(#arrow-action); }
  .edge.observe { stroke: var(--observe); stroke-dasharray: 4 4; opacity: 0.22; }
  .edge.scoped { stroke: var(--scoped); stroke-width: 2; stroke-dasharray: 3 3; opacity: 0.75; }
  .edge.delta { stroke: var(--delta); stroke-width: 2.1; stroke-dasharray: 2 3; opacity: 0.65; }
  .edge.dim { opacity: 0.06; }
  .node { cursor: pointer; }
  .node circle { stroke: #020617; stroke-width: 2; }
  .node.state circle { fill: var(--state); }
  .node.item circle { fill: var(--item); }
  .node.root circle { stroke: #f8fafc; stroke-width: 4; }
  .node text {
    fill: var(--text);
    font-size: 11px;
    pointer-events: none;
    paint-order: stroke;
    stroke: #020617;
    stroke-width: 3px;
    stroke-linejoin: round;
  }
  .node.dim { opacity: 0.12; }
  .node.highlight circle { stroke: #fbbf24; stroke-width: 4; }
  .sidebar {
    border-left: 1px solid var(--line);
    background: #020617;
    overflow: auto;
    padding: 16px;
    min-width: 460px;
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 12px;
  }
  .card h2 { font-size: 15px; margin: 12px 0 8px; }
  .card h2:first-child { margin-top: 0; }
  .kv {
    display: grid;
    grid-template-columns: 150px minmax(0, 1fr);
    gap: 5px 8px;
    font-size: 13px;
  }
  .k { color: var(--muted); }
  .v { overflow-wrap: anywhere; word-break: break-word; white-space: pre-wrap; }
  .list { margin: 8px 0 0; padding-left: 18px; color: var(--text); font-size: 13px; }
  .list li { margin-bottom: 4px; overflow-wrap: anywhere; word-break: break-word; }
  .pill {
    display: inline-block;
    font-size: 12px;
    color: #020617;
    background: var(--observe);
    padding: 2px 7px;
    border-radius: 999px;
    margin: 2px;
  }
  .pill.state { background: var(--state); }
  .pill.item { background: var(--item); }
  .pill.scoped { background: var(--scoped); }
  .pill.delta { background: var(--delta); color: #fff; }
  .small { color: var(--muted); font-size: 12px; }
  @media (max-width: 1000px) {
    .layout { grid-template-columns: 1fr; grid-template-rows: minmax(500px, 1fr) 540px; }
    .sidebar { min-width: 0; border-left: none; border-top: 1px solid var(--line); }
  }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="meta" id="meta"></div>
</header>

<div class="layout">
  <div class="main">
    <div class="toolbar">
      <label><input id="showActions" type="checkbox" checked> verified actions</label>
      <label><input id="showScoped" type="checkbox" checked> scoped items</label>
      <label><input id="showItems" type="checkbox"> all observed</label>
      <label><input id="showDelta" type="checkbox"> delta hints</label>
      <label>depth ≤ <span id="depthValue"></span><input id="depth" type="range" min="0" max="10" value="10"></label>
      <button id="reset">Reset</button>
    </div>

    <svg id="viz" aria-label="agent map visualization">
      <defs>
        <marker id="arrow-action" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#34d399"></path>
        </marker>
      </defs>
      <g id="viewport">
        <g id="edges"></g>
        <g id="nodes"></g>
      </g>
    </svg>
  </div>

  <aside class="sidebar">
    <div class="card">
      <h2>Selection</h2>
      <div id="details" class="small">Click a node or edge.</div>
    </div>

    <div class="card">
      <h2>Legend</h2>
      <div><span class="pill state">state</span> UI state / screen snapshot</div>
      <div><span class="pill item">item</span> observed A11Y item</div>
      <div><span class="pill scoped">scoped</span> best-effort important/active items</div>
      <div><span class="pill delta">delta</span> diagnostic diff hint</div>
      <p class="small">
        Solid green arrows are verified navigation actions.
        Scoped items are best-effort agent-facing visible items.
        Delta is only a diagnostic hint, not the full state content.
      </p>
    </div>

    <div class="card">
      <h2>Stats</h2>
      <div id="stats" class="kv"></div>
    </div>
  </aside>
</div>

<script id="graph-data" type="application/json">__DATA_JSON__</script>
<script>
const data = JSON.parse(document.getElementById("graph-data").textContent);

const svg = document.getElementById("viz");
const edgeLayer = document.getElementById("edges");
const nodeLayer = document.getElementById("nodes");

const showActionsInput = document.getElementById("showActions");
const showItemsInput = document.getElementById("showItems");
const showScopedInput = document.getElementById("showScoped");
const showDeltaInput = document.getElementById("showDelta");
const depthInput = document.getElementById("depth");
const depthValue = document.getElementById("depthValue");
const details = document.getElementById("details");

const rootId = data.root_state_id;
const maxDepth = Math.max(0, ...data.states.map(s => Number(s.depth || 0)));
const previewLimit = 30;
const incomingPreviewLimit = 20;

const layoutMetrics = {
  left: 120,
  top: 110,
  depthStep: 170,
  minStateStep: 46,
  minItemStep: 30,
  bottomPadding: 140,
  rightPadding: 260,
};

depthInput.max = String(maxDepth);
depthInput.value = String(maxDepth);
depthValue.textContent = String(maxDepth);

document.getElementById("meta").textContent =
  `schema=${data.schema_version} · states=${data.states.length} · items=${data.items.length} · action_edges=${data.state_edges.length} · scoped_edges=${data.scoped_item_edges.length}`;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function statsHtml() {
  const s = data.summary || {};
  const rows = [
    ["states", s.states ?? data.states.length],
    ["graph edges", s.edges ?? data.state_edges.length],
    ["canonical items", s.items ?? data.items.length],
    ["observed refs", s.observed_item_refs ?? data.item_edges.length],
    ["scoped refs", s.scoped_observed_item_refs ?? data.scoped_item_edges.length],
    ["delta refs", s.delta_observed_item_refs ?? data.delta_item_edges.length],
    ["state capabilities", s.state_capabilities ?? "—"],
    ["max depth", s.max_depth ?? maxDepth],
    ["pending", s.pending_edges ?? 0],
  ];

  return rows.map(([k, v]) => `<div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(String(v))}</div>`).join("");
}

document.getElementById("stats").innerHTML = statsHtml();

let allNodes = [...data.states, ...data.items];
let nodeById = new Map(allNodes.map(n => [n.id, n]));

function filteredGraph() {
  const maxD = Number(depthInput.value);

  const visibleStates = data.states.filter(s => Number(s.depth || 0) <= maxD);
  const visibleStateIds = new Set(visibleStates.map(s => s.id));

  const actionEdges = showActionsInput.checked
    ? data.state_edges.filter(e => visibleStateIds.has(e.source) && visibleStateIds.has(e.target))
    : [];

  const itemEdges = showItemsInput.checked
    ? data.item_edges.filter(e => visibleStateIds.has(e.source))
    : [];

  const scopedEdges = showScopedInput.checked
    ? data.scoped_item_edges.filter(e => visibleStateIds.has(e.source))
    : [];

  const deltaEdges = showDeltaInput.checked
    ? data.delta_item_edges.filter(e => visibleStateIds.has(e.source))
    : [];

  const visibleItemIds = new Set(
    [...itemEdges, ...scopedEdges, ...deltaEdges].map(e => e.target)
  );

  const nodes = [
    ...visibleStates,
    ...data.items.filter(i => visibleItemIds.has(i.id)),
  ];

  const edges = [
    ...actionEdges,
    ...scopedEdges,
    ...itemEdges,
    ...deltaEdges,
  ];

  return { nodes, edges };
}

function updateCanvasSize(nodes) {
  const states = nodes.filter(n => n.type === "state");
  const items = nodes.filter(n => n.type === "item");

  const statesByDepth = new Map();
  for (const s of states) {
    const d = Number(s.depth || 0);
    if (!statesByDepth.has(d)) statesByDepth.set(d, []);
    statesByDepth.get(d).push(s);
  }

  const maxStatesInDepth = Math.max(1, ...Array.from(statesByDepth.values()).map(arr => arr.length));
  const itemCount = Math.max(1, items.length);
  const maxVisibleDepth = Math.max(0, ...states.map(s => Number(s.depth || 0)));

  const requiredHeight = Math.max(
    800,
    layoutMetrics.top + layoutMetrics.bottomPadding +
      Math.max(maxStatesInDepth * layoutMetrics.minStateStep, itemCount * layoutMetrics.minItemStep)
  );

  const requiredWidth = Math.max(
    1200,
    layoutMetrics.left + layoutMetrics.rightPadding + (maxVisibleDepth + 2) * layoutMetrics.depthStep
  );

  svg.style.width = `${requiredWidth}px`;
  svg.style.height = `${requiredHeight}px`;
  svg.setAttribute("width", String(requiredWidth));
  svg.setAttribute("height", String(requiredHeight));
  svg.setAttribute("viewBox", `0 0 ${requiredWidth} ${requiredHeight}`);

  return { width: requiredWidth, height: requiredHeight };
}

function layout(nodes) {
  const { width, height } = updateCanvasSize(nodes);

  const states = nodes.filter(n => n.type === "state");
  const items = nodes.filter(n => n.type === "item");

  const statesByDepth = new Map();
  for (const s of states) {
    const d = Number(s.depth || 0);
    if (!statesByDepth.has(d)) statesByDepth.set(d, []);
    statesByDepth.get(d).push(s);
  }

  for (const [d, arr] of statesByDepth.entries()) {
    arr.sort((a, b) => String(a.id).localeCompare(String(b.id)));
    const x = layoutMetrics.left + d * layoutMetrics.depthStep;
    const step = Math.max(
      layoutMetrics.minStateStep,
      (height - layoutMetrics.top - layoutMetrics.bottomPadding) / Math.max(1, arr.length)
    );
    arr.forEach((s, idx) => {
      s.x = x;
      s.y = layoutMetrics.top + idx * step;
    });
  }

  const itemX = Math.min(
    width - 180,
    layoutMetrics.left + (maxDepth + 1) * layoutMetrics.depthStep
  );
  items.sort((a, b) => String(a.label).localeCompare(String(b.label)));
  const itemStep = Math.max(
    layoutMetrics.minItemStep,
    (height - layoutMetrics.top - layoutMetrics.bottomPadding) / Math.max(1, items.length)
  );
  items.forEach((i, idx) => {
    i.x = itemX;
    i.y = layoutMetrics.top + idx * itemStep;
  });
}

function render() {
  const fg = filteredGraph();
  layout(fg.nodes);

  const nodes = fg.nodes;
  const edges = fg.edges;
  const visibleNodeIds = new Set(nodes.map(n => n.id));

  edgeLayer.innerHTML = "";
  nodeLayer.innerHTML = "";

  for (const e of edges) {
    const s = nodeById.get(e.source);
    const t = nodeById.get(e.target);
    if (!s || !t || !visibleNodeIds.has(s.id) || !visibleNodeIds.has(t.id)) continue;

    const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const dx = Math.abs(t.x - s.x);
    const c = Math.max(50, dx * 0.45);

    line.setAttribute("d", `M ${s.x} ${s.y} C ${s.x + c} ${s.y}, ${t.x - c} ${t.y}, ${t.x} ${t.y}`);

    const klass = e.type === "verified_action"
      ? "action"
      : e.type === "scoped_observes"
        ? "scoped"
        : e.type === "delta_observes"
          ? "delta"
          : "observe";

    line.setAttribute("class", `edge ${klass}`);
    line.dataset.id = e.id;
    line.addEventListener("click", () => showEdge(e));
    edgeLayer.appendChild(line);
  }

  for (const n of nodes) {
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", `node ${n.type} ${n.id === rootId ? "root" : ""}`);
    g.setAttribute("transform", `translate(${n.x},${n.y})`);
    g.dataset.id = n.id;

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("r", n.type === "state" ? "12" : "8");
    g.appendChild(circle);

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", n.type === "state" ? "16" : "12");
    text.setAttribute("y", "4");
    text.textContent = n.type === "state"
      ? `${n.short_label} (${n.depth})`
      : String(n.short_label).slice(0, 42);
    g.appendChild(text);

    g.addEventListener("click", () => showNode(n));
    nodeLayer.appendChild(g);
  }
}

function actionLine(e) {
  if (!e) return "<li class='small'>none</li>";
  return `<li>${escapeHtml(e.from_state)} -- ${escapeHtml(e.name || e.role || "action")} → this <span class="small">${escapeHtml(e.edge_status || "")}</span></li>`;
}

function listWithMore(items, renderer, limit) {
  const preview = items.slice(0, limit);
  const more = items.length - preview.length;
  const html = preview.map(renderer).join("");
  const tail = more > 0 ? `<li class="small">… ${more} more not shown in preview</li>` : "";

  if (!html) {
    return "<li class='small'>none</li>";
  }

  return html + tail;
}

function capabilityLabel(c) {
  const base = [c.name || c.role || c.kind || "capability", c.description || ""].filter(Boolean).join(" — ");
  if (c.kind === "verified_action" && c.to_state) return `${base} → ${c.to_state}`;
  return base;
}

function showNode(n) {
  highlight(n.id);

  if (n.type === "state") {
    const incoming = n.incoming_actions || [];
    const primaryIncoming = n.primary_incoming_action || null;
    const outgoing = data.state_edges.filter(e => e.source === n.id);
    const observed = data.item_edges.filter(e => e.source === n.id);
    const scoped = data.scoped_item_edges.filter(e => e.source === n.id);
    const delta = data.delta_item_edges.filter(e => e.source === n.id);
    const capabilities = n.state_capabilities || [];

    const activeRoot = n.active_root || {};
    const activeRootText = [activeRoot.kind, activeRoot.role, activeRoot.name].filter(Boolean).join(" / ");

    const incomingHtml = listWithMore(
      incoming,
      e => `<li>${escapeHtml(e.from_state)} -- ${escapeHtml(e.name || e.role || "action")} → this <span class="small">${escapeHtml(e.edge_status || "")}</span></li>`,
      incomingPreviewLimit
    );

    const actionHtml = listWithMore(
      outgoing,
      e => `<li>${escapeHtml(e.label)} → ${escapeHtml(e.target)} <span class="small">${escapeHtml(e.edge_status)}</span></li>`,
      previewLimit
    );

    const capabilityHtml = listWithMore(
      capabilities,
      c => `<li>${escapeHtml(capabilityLabel(c))} <span class="small">${escapeHtml(c.kind || "")}</span></li>`,
      previewLimit
    );

    const scopedHtml = listWithMore(
      scoped,
      e => `<li>${escapeHtml(e.label)} <span class="small">${escapeHtml(e.role)}</span></li>`,
      previewLimit
    );

    const observedHtml = listWithMore(
      observed,
      e => `<li>${escapeHtml(e.label)} <span class="small">${escapeHtml(e.role)}</span></li>`,
      previewLimit
    );

    const deltaHtml = listWithMore(
      delta,
      e => `<li>${escapeHtml(e.label)} <span class="small">${escapeHtml(e.role)}</span></li>`,
      previewLimit
    );

    details.innerHTML = `
      <div class="kv">
        <div class="k">type</div><div class="v">state</div>
        <div class="k">id</div><div class="v">${escapeHtml(n.id)}</div>
        <div class="k">label</div><div class="v">${escapeHtml(n.short_label)}</div>
        <div class="k">depth</div><div class="v">${escapeHtml(n.depth)}</div>
        <div class="k">active root</div><div class="v">${escapeHtml(activeRootText || "—")}</div>
        <div class="k">incoming</div><div class="v">${n.incoming_count}</div>
        <div class="k">verified</div><div class="v">${n.verified_count}</div>
        <div class="k">capabilities</div><div class="v">${n.capabilities_count}</div>
        <div class="k">scoped</div><div class="v">${n.scoped_count}</div>
        <div class="k">scoped source</div><div class="v">${escapeHtml(n.scoped_observed_source || "—")}</div>
        <div class="k">confidence</div><div class="v">${escapeHtml(n.scoped_observed_confidence || "—")}</div>
        <div class="k">observed</div><div class="v">${n.observed_count}</div>
        <div class="k">delta</div><div class="v">${n.delta_count}</div>
        <div class="k">delta base</div><div class="v">${escapeHtml(n.delta_base_state || "—")}</div>
      </div>

      <h2>Primary incoming action</h2>
      <ul class="list">${actionLine(primaryIncoming)}</ul>

      <h2>State capabilities</h2>
      <ul class="list">${capabilityHtml}</ul>

      <h2>Verified actions</h2>
      <ul class="list">${actionHtml}</ul>

      <h2>Scoped observed items</h2>
      <ul class="list">${scopedHtml}</ul>

      <h2>All observed items</h2>
      <ul class="list">${observedHtml}</ul>

      <h2>Delta hints</h2>
      <ul class="list">${deltaHtml}</ul>

      <h2>Incoming actions</h2>
      <ul class="list">${incomingHtml}</ul>
    `;
  } else {
    details.innerHTML = `
      <div class="kv">
        <div class="k">type</div><div class="v">item</div>
        <div class="k">id</div><div class="v">${escapeHtml(n.id)}</div>
        <div class="k">role</div><div class="v">${escapeHtml(n.role)}</div>
        <div class="k">name</div><div class="v">${escapeHtml(n.name)}</div>
        <div class="k">description</div><div class="v">${escapeHtml(n.description)}</div>
        <div class="k">status</div><div class="v">${escapeHtml(n.status)}</div>
        <div class="k">bbox hint</div><div class="v">${n.has_visible_bbox_hint ? "yes" : "no"}</div>
        <div class="k">path tail</div><div class="v">${escapeHtml((n.parent_path_tail || []).join(" / "))}</div>
      </div>
    `;
  }
}

function showEdge(e) {
  highlight(e.source, e.target);

  details.innerHTML = `
    <div class="kv">
      <div class="k">type</div><div class="v">${escapeHtml(e.type)}</div>
      <div class="k">label</div><div class="v">${escapeHtml(e.label)}</div>
      <div class="k">source</div><div class="v">${escapeHtml(e.source)}</div>
      <div class="k">target</div><div class="v">${escapeHtml(e.target)}</div>
      <div class="k">role</div><div class="v">${escapeHtml(e.role || "")}</div>
      <div class="k">status</div><div class="v">${escapeHtml(e.edge_status || "")}</div>
      <div class="k">method</div><div class="v">${escapeHtml(e.method || "")}</div>
      <div class="k">bbox</div><div class="v">${e.has_bbox ? "yes" : "no"}</div>
    </div>
  `;
}

function highlight(...ids) {
  const wanted = new Set(ids);

  for (const g of nodeLayer.querySelectorAll(".node")) {
    const id = g.dataset.id;
    g.classList.toggle("highlight", wanted.has(id));
    g.classList.toggle("dim", wanted.size > 0 && !wanted.has(id));
  }

  for (const e of edgeLayer.querySelectorAll(".edge")) {
    e.classList.toggle("dim", wanted.size > 0);
  }
}

function resetView() {
  showActionsInput.checked = true;
  showScopedInput.checked = true;
  showItemsInput.checked = false;
  showDeltaInput.checked = false;
  depthInput.value = String(maxDepth);
  depthValue.textContent = String(maxDepth);
  details.innerHTML = "Click a node or edge.";
  render();
}

for (const el of [showActionsInput, showItemsInput, showScopedInput, showDeltaInput, depthInput]) {
  el.addEventListener("input", () => {
    depthValue.textContent = depthInput.value;
    render();
  });
}

document.getElementById("reset").addEventListener("click", resetView);
window.addEventListener("resize", render);

render();
</script>
</body>
</html>
"""
    return (
        template
        .replace("__TITLE__", html.escape(title))
        .replace("__DATA_JSON__", data_json)
    )


def visualize_agent_map(
    app: str,
    maps_dir: Path,
    output: Path | None,
    *,
    max_items_per_state: int,
) -> Path:
    agent_map = _load_agent_map(app, maps_dir)
    data = _build_visual_data(
        agent_map,
        max_items_per_state=max_items_per_state,
    )

    if output is None:
        output = maps_dir / app / "agent_map.html"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_html_document(data), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build interactive HTML visualization for agent_map.json."
    )
    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--max-items-per-state",
        type=int,
        default=200,
        help=(
            "Limit observed/scoped item refs rendered per state to keep the HTML responsive. "
            "This affects graph rendering, not the sidebar preview."
        ),
    )

    args = parser.parse_args()

    output = visualize_agent_map(
        app=args.app,
        maps_dir=Path(args.maps),
        output=Path(args.output) if args.output else None,
        max_items_per_state=args.max_items_per_state,
    )

    print(json.dumps({
        "ok": True,
        "app_id": args.app,
        "output": str(output),
    }, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
