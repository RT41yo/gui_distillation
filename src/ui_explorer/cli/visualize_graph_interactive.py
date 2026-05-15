from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape


KIND_COLORS = {
    "main": "#4C78A8",
    "menu": "#F58518",
    "dialog": "#E45756",
    "window_overlay": "#72B7B2",
    "unknown": "#9D9D9D",
}

STATUS_COLORS = {
    "confirmed": "#2ca25f",
    "pending": "#9e9e9e",
    "failed_navigation": "#de2d26",
    "same_state": "#756bb1",
}


def load_graph(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def node_kind(node: dict) -> str:
    active = node.get("active_root") or {}
    return (active.get("kind") or "unknown").strip() or "unknown"


def node_title(node_id: str, node: dict) -> str:
    active = node.get("active_root") or {}

    name = (active.get("name") or "").strip()
    role = (active.get("role") or "").strip()
    kind = node_kind(node)

    if name:
        return name

    if role:
        return role

    return kind or node_id


def compact_node_label(node_id: str, node: dict, pending_count: int) -> str:
    title = node_title(node_id, node)
    depth = node.get("depth", "?")
    kind = node_kind(node)

    if len(title) > 22:
        title = title[:21] + "…"

    lines = [
        title,
        node_id,
        f"d={depth}, {kind}",
    ]

    if pending_count:
        lines.append(f"pending={pending_count}")

    return "\\n".join(lines)


def edge_action_label(edge: dict) -> str:
    action = edge.get("action") or {}
    name = (action.get("name") or "").strip()
    role = (action.get("role") or "").strip()

    if name:
        return name

    if role:
        return role

    return edge.get("action_key") or edge.get("edge_id") or "action"


def edge_status(edge: dict) -> str:
    return (edge.get("status") or "unknown").strip() or "unknown"


def depth_counts(nodes: dict) -> dict[str, int]:
    counts = Counter()

    for node in nodes.values():
        counts[str(node.get("depth", "?"))] += 1

    return dict(sorted(counts.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 999))


def status_counts(edges: dict) -> dict[str, int]:
    counts = Counter()

    for edge in edges.values():
        counts[edge_status(edge)] += 1

    return dict(sorted(counts.items()))


def outgoing_counts(edges: dict) -> dict[str, Counter]:
    result: dict[str, Counter] = defaultdict(Counter)

    for edge in edges.values():
        from_state = edge.get("from_state")
        if not from_state:
            continue

        result[from_state][edge_status(edge)] += 1

    return result


def build_elements(graph: dict, *, include_pending_stubs: bool = False) -> tuple[list[dict], dict]:
    nodes = graph.get("nodes") or {}
    edges = graph.get("edges") or {}

    out_counts = outgoing_counts(edges)

    elements: list[dict] = []

    for node_id, node in nodes.items():
        kind = node_kind(node)
        active = node.get("active_root") or {}
        counts = out_counts.get(node_id, Counter())
        pending_count = counts.get("pending", 0)

        elements.append({
            "group": "nodes",
            "data": {
                "id": node_id,
                "label": compact_node_label(node_id, node, pending_count),
                "title": node_title(node_id, node),
                "kind": kind,
                "depth": int(node.get("depth", 0)),
                "role": active.get("role") or "",
                "active_name": active.get("name") or "",
                "pending": pending_count,
                "confirmed": counts.get("confirmed", 0),
                "same_state": counts.get("same_state", 0),
                "failed_navigation": counts.get("failed_navigation", 0),
                "action_count": node.get("action_count", node.get("actions_count", 0)),
                "color": KIND_COLORS.get(kind, KIND_COLORS["unknown"]),
            },
        })

    pending_stub_index = 0

    for edge_id, edge in edges.items():
        source = edge.get("from_state")
        target = edge.get("to_state")
        status = edge_status(edge)

        if not source:
            continue

        # Pending edges usually have no to_state yet. Drawing all of them as
        # separate stubs makes the graph noisy, so by default they are shown
        # in the node details panel and as pending=N on the node.
        if not target:
            if status == "same_state":
                target = source
            elif include_pending_stubs and status == "pending":
                pending_stub_index += 1
                target = f"__pending_stub_{pending_stub_index}"

                elements.append({
                    "group": "nodes",
                    "data": {
                        "id": target,
                        "label": f"pending\\n{edge_action_label(edge)}",
                        "title": "pending target",
                        "kind": "unknown",
                        "depth": int(nodes.get(source, {}).get("depth", 0)) + 1,
                        "role": "",
                        "active_name": "",
                        "pending": 0,
                        "confirmed": 0,
                        "same_state": 0,
                        "failed_navigation": 0,
                        "action_count": 0,
                        "color": "#eeeeee",
                        "is_stub": True,
                    },
                })
            else:
                continue

        if source not in nodes and not source.startswith("__pending_stub_"):
            continue

        if target not in nodes and not target.startswith("__pending_stub_"):
            continue

        action = edge.get("action") or {}

        elements.append({
            "group": "edges",
            "data": {
                "id": edge_id,
                "source": source,
                "target": target,
                "label": edge_action_label(edge),
                "status": status,
                "priority": edge.get("priority"),
                "created_order": edge.get("created_order"),
                "action_key": edge.get("action_key") or action.get("action_key") or "",
                "action_name": action.get("name") or "",
                "action_role": action.get("role") or "",
                "color": STATUS_COLORS.get(status, "#999999"),
            },
        })

    outgoing_by_node: dict[str, list[dict]] = defaultdict(list)

    for edge_id, edge in sorted(
        edges.items(),
        key=lambda item: (
            int(item[1].get("created_order", 10**9)),
            item[0],
        ),
    ):
        from_state = edge.get("from_state")
        if not from_state:
            continue

        action = edge.get("action") or {}

        outgoing_by_node[from_state].append({
            "edge_id": edge_id,
            "status": edge_status(edge),
            "to_state": edge.get("to_state"),
            "priority": edge.get("priority"),
            "created_order": edge.get("created_order"),
            "action_key": edge.get("action_key") or action.get("action_key"),
            "action_name": action.get("name"),
            "action_role": action.get("role"),
            "description": action.get("description"),
            "bbox": action.get("bbox"),
        })

    return elements, outgoing_by_node


def graph_summary(graph: dict) -> dict:
    nodes = graph.get("nodes") or {}
    edges = graph.get("edges") or {}

    max_depth = 0
    for node in nodes.values():
        try:
            max_depth = max(max_depth, int(node.get("depth", 0)))
        except Exception:
            pass

    return {
        "app_id": graph.get("app_id"),
        "root_state_id": graph.get("root_state_id"),
        "nodes": len(nodes),
        "edges": len(edges),
        "depth_counts": depth_counts(nodes),
        "status_counts": status_counts(edges),
        "max_depth": max_depth,
        "completion": graph.get("completion") or {},
    }


def write_html(graph: dict, output_path: Path, *, include_pending_stubs: bool = False) -> None:
    elements, outgoing_by_node = build_elements(
        graph,
        include_pending_stubs=include_pending_stubs,
    )
    summary = graph_summary(graph)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>GUI Exploration Interactive Graph</title>

  <script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
  <script src="https://unpkg.com/dagre@0.8.5/dist/dagre.min.js"></script>
  <script src="https://unpkg.com/cytoscape-dagre@2.5.0/cytoscape-dagre.js"></script>

  <style>
    body {{
      margin: 0;
      font-family: Inter, Arial, sans-serif;
      background: #f7f7f7;
      color: #222;
      overflow: hidden;
    }}

    #app {{
      display: grid;
      grid-template-columns: 320px 1fr 390px;
      height: 100vh;
      width: 100vw;
    }}

    aside {{
      background: #ffffff;
      border-right: 1px solid #ddd;
      padding: 16px;
      overflow: auto;
    }}

    #details {{
      border-right: none;
      border-left: 1px solid #ddd;
    }}

    h1 {{
      font-size: 18px;
      margin: 0 0 12px 0;
    }}

    h2 {{
      font-size: 14px;
      margin: 20px 0 8px 0;
      border-bottom: 1px solid #eee;
      padding-bottom: 6px;
    }}

    .summary-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 12px;
    }}

    .card {{
      background: #f4f6f8;
      border: 1px solid #e1e4e8;
      border-radius: 8px;
      padding: 8px;
      font-size: 13px;
    }}

    .card strong {{
      display: block;
      font-size: 18px;
    }}

    label {{
      display: block;
      margin: 8px 0;
      font-size: 13px;
    }}

    input[type="number"] {{
      width: 70px;
    }}

    button {{
      margin: 4px 4px 4px 0;
      padding: 7px 9px;
      border: 1px solid #ccc;
      border-radius: 7px;
      background: #fff;
      cursor: pointer;
      font-size: 12px;
    }}

    button:hover {{
      background: #f0f0f0;
    }}

    #cy {{
      height: 100vh;
      width: 100%;
      background: #fbfbfb;
    }}

    code {{
      background: #f2f2f2;
      padding: 1px 4px;
      border-radius: 4px;
    }}

    .small {{
      color: #666;
      font-size: 12px;
      line-height: 1.35;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 6px 0;
      font-size: 13px;
    }}

    .swatch {{
      width: 14px;
      height: 14px;
      border-radius: 3px;
      border: 1px solid #777;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }}

    td, th {{
      border-bottom: 1px solid #eee;
      padding: 5px 3px;
      vertical-align: top;
      text-align: left;
    }}

    th {{
      color: #555;
      font-weight: 600;
    }}

    .edge-status {{
      font-weight: 600;
      white-space: nowrap;
    }}

    .muted {{
      color: #777;
    }}

    .details-block {{
      background: #fafafa;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      padding: 10px;
      margin: 8px 0;
      overflow-wrap: anywhere;
    }}
  </style>
</head>

<body>
<div id="app">
  <aside>
    <h1>GUI Graph</h1>

    <div class="summary-grid">
      <div class="card"><span>Nodes</span><strong id="summaryNodes"></strong></div>
      <div class="card"><span>Edges</span><strong id="summaryEdges"></strong></div>
      <div class="card"><span>Max depth</span><strong id="summaryDepth"></strong></div>
      <div class="card"><span>Root</span><strong id="summaryRoot" style="font-size:11px"></strong></div>
    </div>

    <h2>Filters</h2>

    <label>
      Max depth:
      <input id="maxDepth" type="number" min="0" value="{summary["max_depth"]}">
    </label>

    <label><input class="status-filter" type="checkbox" value="confirmed" checked> confirmed</label>
    <label><input class="status-filter" type="checkbox" value="same_state" checked> same_state</label>
    <label><input class="status-filter" type="checkbox" value="failed_navigation" checked> failed_navigation</label>
    <label><input class="status-filter" type="checkbox" value="pending" checked> pending stubs</label>

    <label><input id="showLabels" type="checkbox" checked> show node labels</label>
    <label><input id="showEdgeLabels" type="checkbox"> show edge labels</label>

    <h2>Layout</h2>
    <button onclick="runLayout('dagre')">Dagre</button>
    <button onclick="runLayout('breadthfirst')">Breadthfirst</button>
    <button onclick="runLayout('cose')">Force</button>
    <button onclick="fitGraph()">Fit</button>

    <h2>Depth counts</h2>
    <div id="depthCounts"></div>

    <h2>Status counts</h2>
    <div id="statusCounts"></div>

    <h2>Legend</h2>
    <div id="legend"></div>

    <p class="small">
      Pending edges without known target are not drawn as regular edges by default.
      They are shown as <code>pending=N</code> in node labels and in the node details panel.
    </p>
  </aside>

  <main>
    <div id="cy"></div>
  </main>

  <aside id="details">
    <h1>Details</h1>
    <div id="selectedDetails" class="small">
      Click a node or edge to inspect it.
    </div>
  </aside>
</div>

<script>
const graphSummary = {json.dumps(summary, ensure_ascii=False)};
const elements = {json.dumps(elements, ensure_ascii=False)};
const outgoingByNode = {json.dumps(outgoing_by_node, ensure_ascii=False)};
const kindColors = {json.dumps(KIND_COLORS, ensure_ascii=False)};
const statusColors = {json.dumps(STATUS_COLORS, ensure_ascii=False)};

document.getElementById("summaryNodes").textContent = graphSummary.nodes;
document.getElementById("summaryEdges").textContent = graphSummary.edges;
document.getElementById("summaryDepth").textContent = graphSummary.max_depth;
document.getElementById("summaryRoot").textContent = graphSummary.root_state_id || "";

function renderCounts() {{
  const depthDiv = document.getElementById("depthCounts");
  depthDiv.innerHTML = Object.entries(graphSummary.depth_counts)
    .map(([k, v]) => `<div class="legend-item"><code>depth ${{k}}</code> ${{v}}</div>`)
    .join("");

  const statusDiv = document.getElementById("statusCounts");
  statusDiv.innerHTML = Object.entries(graphSummary.status_counts)
    .map(([k, v]) => `<div class="legend-item"><code>${{k}}</code> ${{v}}</div>`)
    .join("");

  const legendDiv = document.getElementById("legend");
  legendDiv.innerHTML = Object.entries(kindColors)
    .map(([kind, color]) => `
      <div class="legend-item">
        <span class="swatch" style="background:${{color}}"></span>
        <span>${{kind}}</span>
      </div>
    `)
    .join("");
}}

renderCounts();

const cy = cytoscape({{
  container: document.getElementById("cy"),
  elements,

  wheelSensitivity: 0.18,

  style: [
    {{
      selector: "node",
      style: {{
        "shape": "round-rectangle",
        "background-color": "data(color)",
        "border-color": "#1f1f1f",
        "border-width": 1,
        "label": "data(label)",
        "font-size": 9,
        "text-wrap": "wrap",
        "text-max-width": 110,
        "text-valign": "center",
        "text-halign": "center",
        "color": "#111",
        "width": ele => 78 + Math.min((ele.data("pending") || 0) * 4, 40),
        "height": ele => 42 + Math.min((ele.data("pending") || 0) * 3, 30),
        "padding": "7px",
        "overlay-padding": "6px"
      }}
    }},
    {{
      selector: 'node[is_stub]',
      style: {{
        "background-color": "#eeeeee",
        "border-style": "dashed",
        "border-color": "#999",
        "color": "#666"
      }}
    }},
    {{
      selector: "edge",
      style: {{
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "target-arrow-color": "data(color)",
        "line-color": "data(color)",
        "width": 1.4,
        "opacity": 0.58,
        "label": "",
        "font-size": 8,
        "text-rotation": "autorotate",
        "text-background-opacity": 0.75,
        "text-background-color": "#ffffff",
        "text-background-padding": "2px"
      }}
    }},
    {{
      selector: 'edge[status = "same_state"]',
      style: {{
        "line-style": "dashed",
        "opacity": 0.45
      }}
    }},
    {{
      selector: 'edge[status = "failed_navigation"]',
      style: {{
        "line-style": "dotted",
        "width": 2,
        "opacity": 0.8
      }}
    }},
    {{
      selector: ".hidden-by-filter",
      style: {{
        "display": "none"
      }}
    }},
    {{
      selector: ".selected",
      style: {{
        "border-width": 4,
        "border-color": "#000",
        "opacity": 1,
        "z-index": 999
      }}
    }},
    {{
      selector: "edge.selected",
      style: {{
        "width": 4,
        "opacity": 1,
        "z-index": 999
      }}
    }},
    {{
      selector: ".faded",
      style: {{
        "opacity": 0.12
      }}
    }}
  ],

  layout: {{
    name: "dagre",
    rankDir: "LR",
    nodeSep: 55,
    edgeSep: 12,
    rankSep: 130,
    animate: false
  }}
}});

function runLayout(name) {{
  let options;

  if (name === "dagre") {{
    options = {{
      name: "dagre",
      rankDir: "LR",
      nodeSep: 55,
      edgeSep: 12,
      rankSep: 130,
      animate: true,
      animationDuration: 350
    }};
  }} else if (name === "breadthfirst") {{
    options = {{
      name: "breadthfirst",
      directed: true,
      spacingFactor: 1.25,
      animate: true,
      animationDuration: 350
    }};
  }} else {{
    options = {{
      name: "cose",
      animate: true,
      animationDuration: 500,
      nodeRepulsion: 120000,
      idealEdgeLength: 130,
      edgeElasticity: 0.12
    }};
  }}

  cy.layout(options).run();
}}

function fitGraph() {{
  cy.fit(undefined, 40);
}}

function selectedStatuses() {{
  return new Set(
    Array.from(document.querySelectorAll(".status-filter"))
      .filter(el => el.checked)
      .map(el => el.value)
  );
}}

function applyFilters() {{
  const maxDepth = Number(document.getElementById("maxDepth").value);
  const statuses = selectedStatuses();
  const showLabels = document.getElementById("showLabels").checked;
  const showEdgeLabels = document.getElementById("showEdgeLabels").checked;

  cy.elements().removeClass("hidden-by-filter");

  cy.nodes().forEach(node => {{
    const depth = Number(node.data("depth") || 0);
    if (depth > maxDepth) {{
      node.addClass("hidden-by-filter");
    }}
  }});

  cy.edges().forEach(edge => {{
    const status = edge.data("status");
    const sourceHidden = edge.source().hasClass("hidden-by-filter");
    const targetHidden = edge.target().hasClass("hidden-by-filter");

    if (!statuses.has(status) || sourceHidden || targetHidden) {{
      edge.addClass("hidden-by-filter");
    }}
  }});

  cy.style()
    .selector("node")
    .style("label", showLabels ? "data(label)" : "")
    .selector("edge")
    .style("label", showEdgeLabels ? "data(label)" : "")
    .update();
}}

document.getElementById("maxDepth").addEventListener("change", applyFilters);
document.getElementById("showLabels").addEventListener("change", applyFilters);
document.getElementById("showEdgeLabels").addEventListener("change", applyFilters);
document.querySelectorAll(".status-filter").forEach(el => {{
  el.addEventListener("change", applyFilters);
}});

function htmlEscape(value) {{
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}}

function renderNodeDetails(node) {{
  const d = node.data();
  const outgoing = outgoingByNode[d.id] || [];

  const rows = outgoing.map(edge => `
    <tr>
      <td><span class="edge-status" style="color:${{statusColors[edge.status] || "#555"}}">${{htmlEscape(edge.status)}}</span></td>
      <td>${{htmlEscape(edge.action_name || edge.action_role || edge.action_key || "")}}</td>
      <td>${{htmlEscape(edge.to_state || "unknown")}}</td>
    </tr>
  `).join("");

  document.getElementById("selectedDetails").innerHTML = `
    <div class="details-block">
      <strong>Node</strong><br>
      <code>${{htmlEscape(d.id)}}</code>
    </div>

    <table>
      <tr><th>title</th><td>${{htmlEscape(d.title)}}</td></tr>
      <tr><th>kind</th><td>${{htmlEscape(d.kind)}}</td></tr>
      <tr><th>depth</th><td>${{htmlEscape(d.depth)}}</td></tr>
      <tr><th>role</th><td>${{htmlEscape(d.role)}}</td></tr>
      <tr><th>active name</th><td>${{htmlEscape(d.active_name)}}</td></tr>
      <tr><th>confirmed out</th><td>${{htmlEscape(d.confirmed)}}</td></tr>
      <tr><th>pending out</th><td>${{htmlEscape(d.pending)}}</td></tr>
      <tr><th>same_state out</th><td>${{htmlEscape(d.same_state)}}</td></tr>
    </table>

    <h2>Outgoing edges</h2>
    <table>
      <thead>
        <tr><th>Status</th><th>Action</th><th>To</th></tr>
      </thead>
      <tbody>
        ${{rows || '<tr><td colspan="3" class="muted">No outgoing edges</td></tr>'}}
      </tbody>
    </table>
  `;
}}

function renderEdgeDetails(edge) {{
  const d = edge.data();

  document.getElementById("selectedDetails").innerHTML = `
    <div class="details-block">
      <strong>Edge</strong><br>
      <code>${{htmlEscape(d.id)}}</code>
    </div>

    <table>
      <tr><th>status</th><td>${{htmlEscape(d.status)}}</td></tr>
      <tr><th>action</th><td>${{htmlEscape(d.label)}}</td></tr>
      <tr><th>role</th><td>${{htmlEscape(d.action_role)}}</td></tr>
      <tr><th>action key</th><td><code>${{htmlEscape(d.action_key)}}</code></td></tr>
      <tr><th>source</th><td><code>${{htmlEscape(d.source)}}</code></td></tr>
      <tr><th>target</th><td><code>${{htmlEscape(d.target)}}</code></td></tr>
      <tr><th>priority</th><td>${{htmlEscape(d.priority)}}</td></tr>
      <tr><th>created order</th><td>${{htmlEscape(d.created_order)}}</td></tr>
    </table>
  `;
}}

cy.on("tap", "node", evt => {{
  const node = evt.target;

  cy.elements().removeClass("selected faded");
  cy.elements().addClass("faded");
  node.removeClass("faded").addClass("selected");
  node.connectedEdges().removeClass("faded").addClass("selected");
  node.connectedEdges().connectedNodes().removeClass("faded");

  renderNodeDetails(node);
}});

cy.on("tap", "edge", evt => {{
  const edge = evt.target;

  cy.elements().removeClass("selected faded");
  cy.elements().addClass("faded");
  edge.removeClass("faded").addClass("selected");
  edge.connectedNodes().removeClass("faded").addClass("selected");

  renderEdgeDetails(edge);
}});

cy.on("tap", evt => {{
  if (evt.target === cy) {{
    cy.elements().removeClass("selected faded");
    document.getElementById("selectedDetails").innerHTML =
      '<span class="small">Click a node or edge to inspect it.</span>';
  }}
}});

applyFilters();
setTimeout(() => cy.fit(undefined, 40), 400);
</script>
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate interactive Cytoscape.js visualization for GUI exploration graph."
    )
    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--include-pending-stubs",
        action="store_true",
        help="Draw pending edges without to_state as stub nodes. Usually too noisy.",
    )

    args = parser.parse_args()

    graph_path = Path(args.maps) / args.app / "graph.json"

    if not graph_path.exists():
        print(f"graph.json not found: {graph_path}", file=sys.stderr)
        return 2

    output_path = (
        Path(args.output)
        if args.output
        else Path(args.maps) / args.app / "graph_interactive.html"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph = load_graph(graph_path)

    write_html(
        graph,
        output_path,
        include_pending_stubs=args.include_pending_stubs,
    )

    print(json.dumps(
        {
            "ok": True,
            "graph": str(graph_path),
            "output": str(output_path),
        },
        indent=2,
        ensure_ascii=False,
    ))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
