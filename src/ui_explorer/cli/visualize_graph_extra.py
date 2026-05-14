from __future__ import annotations

import argparse
import json
import math
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


def node_label(node_id: str, node: dict) -> str:
    active = node.get("active_root") or {}
    kind = active.get("kind") or "unknown"
    name = active.get("name") or ""
    role = active.get("role") or ""

    if name:
        title = name
    elif role:
        title = role
    else:
        title = kind

    return f"{title}\\n{node_id}"


def node_kind(node: dict) -> str:
    return ((node.get("active_root") or {}).get("kind") or "unknown").strip() or "unknown"


def confirmed_edges(graph: dict) -> list[dict]:
    return [
        e for e in graph.get("edges", {}).values()
        if e.get("status") == "confirmed" and e.get("to_state")
    ]


def pending_counts_by_node(graph: dict) -> Counter:
    counts = Counter()

    for edge in graph.get("edges", {}).values():
        if edge.get("status") == "pending":
            counts[edge.get("from_state")] += 1

    return counts


def write_sankey_html(graph: dict, output_path: Path) -> None:
    nodes = graph.get("nodes", {})
    edges = confirmed_edges(graph)

    # Aggregated flow by depth/kind.
    links = Counter()

    for edge in edges:
        src_id = edge.get("from_state")
        dst_id = edge.get("to_state")

        if src_id not in nodes or dst_id not in nodes:
            continue

        src = nodes[src_id]
        dst = nodes[dst_id]

        src_key = f"D{src.get('depth')} · {node_kind(src)}"
        dst_key = f"D{dst.get('depth')} · {node_kind(dst)}"

        if src_key != dst_key:
            links[(src_key, dst_key)] += 1

    labels = sorted({x for pair in links for x in pair})
    index = {label: i for i, label in enumerate(labels)}

    sources = [index[src] for src, _ in links]
    targets = [index[dst] for _, dst in links]
    values = list(links.values())

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>GUI Exploration Sankey</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{
      margin: 0;
      font-family: Inter, Arial, sans-serif;
      background: #fafafa;
      color: #222;
    }}
    header {{
      padding: 22px 28px 8px 28px;
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      font-weight: 700;
    }}
    p {{
      margin: 8px 0 0 0;
      color: #555;
      font-size: 14px;
    }}
    #chart {{
      width: 100vw;
      height: calc(100vh - 90px);
    }}
  </style>
</head>
<body>
<header>
  <h1>GUI Exploration Flow by Depth and State Type</h1>
  <p>Aggregated confirmed transitions: depth/kind → depth/kind</p>
</header>
<div id="chart"></div>
<script>
const data = [{{
  type: "sankey",
  arrangement: "snap",
  node: {{
    pad: 22,
    thickness: 18,
    line: {{ color: "rgba(0,0,0,0.25)", width: 0.5 }},
    label: {json.dumps(labels, ensure_ascii=False)}
  }},
  link: {{
    source: {json.dumps(sources)},
    target: {json.dumps(targets)},
    value: {json.dumps(values)}
  }}
}}];

const layout = {{
  paper_bgcolor: "#fafafa",
  plot_bgcolor: "#fafafa",
  font: {{ size: 13 }},
  margin: {{ l: 30, r: 30, t: 20, b: 30 }}
}};

Plotly.newPlot("chart", data, layout, {{responsive: true}});
</script>
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")


def write_frontier_pdf(graph: dict, output_path: Path) -> None:
    import matplotlib.pyplot as plt

    nodes = graph.get("nodes", {})
    pending = pending_counts_by_node(graph)

    rows = []
    for node_id, count in pending.items():
        node = nodes.get(node_id)
        if not node:
            continue

        depth = node.get("depth")
        kind = node_kind(node)
        label = node_label(node_id, node).replace("\\n", " / ")

        rows.append((depth, count, kind, label, node_id))

    rows.sort(key=lambda x: (x[0], -x[1], x[3]))
    rows = rows[:24]

    if not rows:
        rows = [(0, 0, "unknown", "No pending frontier", "")]

    labels = [f"D{depth} · {kind} · {node_id}" for depth, count, kind, label, node_id in rows]
    values = [count for depth, count, kind, label, node_id in rows]

    height = max(5.0, 0.36 * len(rows) + 1.8)

    fig, ax = plt.subplots(figsize=(12, height))
    ax.barh(range(len(rows)), values)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Pending edges")
    ax.set_title("Pending Frontier by State", fontsize=15, fontweight="bold")

    for i, value in enumerate(values):
        ax.text(value + 0.15, i, str(value), va="center", fontsize=8)

    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, format="pdf", bbox_inches="tight")
    plt.close(fig)


def write_metro_pdf(graph: dict, output_path: Path) -> None:
    import networkx as nx
    import matplotlib.pyplot as plt

    nodes = graph.get("nodes", {})
    edges = confirmed_edges(graph)
    pending = pending_counts_by_node(graph)

    G = nx.DiGraph()

    for node_id, node in nodes.items():
        G.add_node(
            node_id,
            depth=node.get("depth", 0),
            kind=node_kind(node),
            label=node_label(node_id, node),
            pending=pending.get(node_id, 0),
        )

    for edge in edges:
        src = edge.get("from_state")
        dst = edge.get("to_state")

        if src in G and dst in G:
            action = edge.get("action") or {}
            edge_label = action.get("name") or action.get("role") or ""
            G.add_edge(src, dst, label=edge_label)

    depths = defaultdict(list)
    for node_id, data in G.nodes(data=True):
        depths[data["depth"]].append(node_id)

    pos = {}
    max_depth = max(depths.keys()) if depths else 0

    for depth in range(max_depth + 1):
        layer = sorted(depths.get(depth, []))
        n = len(layer)

        for i, node_id in enumerate(layer):
            y = 0 if n == 1 else (n - 1) / 2 - i
            pos[node_id] = (depth * 4.5, y * 1.35)

    fig_width = max(12, 4.5 * (max_depth + 1))
    fig_height = max(7, max(len(v) for v in depths.values()) * 0.85)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    for depth in range(max_depth + 1):
        ax.axvline(depth * 4.5, color="#e6e6e6", linewidth=1)
        ax.text(
            depth * 4.5,
            max(y for _, y in pos.values()) + 1.1,
            f"depth {depth}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
            color="#444",
        )

    for src, dst, data in G.edges(data=True):
        x1, y1 = pos[src]
        x2, y2 = pos[dst]

        ax.annotate(
            "",
            xy=(x2 - 0.55, y2),
            xytext=(x1 + 0.55, y1),
            arrowprops=dict(
                arrowstyle="->",
                lw=1.1,
                color="#777",
                alpha=0.65,
                shrinkA=6,
                shrinkB=6,
            ),
        )

    for node_id, data in G.nodes(data=True):
        x, y = pos[node_id]
        kind = data["kind"]
        color = KIND_COLORS.get(kind, KIND_COLORS["unknown"])
        pcount = data["pending"]

        radius = 0.34 + min(math.sqrt(pcount) * 0.035, 0.25)

        circle = plt.Circle(
            (x, y),
            radius,
            facecolor=color,
            edgecolor="#222",
            linewidth=0.8,
            alpha=0.92,
        )
        ax.add_patch(circle)

        active = nodes[node_id].get("active_root") or {}
        title = active.get("name") or active.get("role") or kind
        short = title[:22] + "…" if len(title) > 22 else title

        label = f"{short}\\n{node_id}"
        if pcount:
            label += f"\\npending={pcount}"

        ax.text(
            x,
            y - radius - 0.12,
            label,
            ha="center",
            va="top",
            fontsize=7.5,
            color="#222",
        )

    legend_x = -0.4
    legend_y = min(y for _, y in pos.values()) - 1.2 if pos else -1

    for i, (kind, color) in enumerate(KIND_COLORS.items()):
        ax.scatter(
            legend_x + i * 1.6,
            legend_y,
            s=95,
            color=color,
            edgecolor="#222",
            linewidth=0.5,
        )
        ax.text(
            legend_x + i * 1.6 + 0.18,
            legend_y,
            kind,
            va="center",
            fontsize=8,
        )

    ax.set_title(
        "GUI Exploration Metro Map - Confirmed Transitions",
        fontsize=16,
        fontweight="bold",
        pad=20,
    )
    ax.set_axis_off()

    if pos:
        xs = [x for x, _ in pos.values()]
        ys = [y for _, y in pos.values()]
        ax.set_xlim(min(xs) - 1.8, max(xs) + 1.8)
        ax.set_ylim(min(ys) - 2.2, max(ys) + 1.8)

    fig.tight_layout()
    fig.savefig(output_path, format="pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate additional graph visualizations: Sankey HTML, frontier PDF, metro PDF."
    )
    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    graph_path = Path(args.maps) / args.app / "graph.json"

    if not graph_path.exists():
        print(f"graph.json not found: {graph_path}", file=sys.stderr)
        return 2

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(args.maps) / args.app
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    graph = load_graph(graph_path)

    sankey_path = output_dir / "graph_sankey.html"
    frontier_path = output_dir / "graph_frontier.pdf"
    metro_path = output_dir / "graph_metro.pdf"

    write_sankey_html(graph, sankey_path)
    write_frontier_pdf(graph, frontier_path)
    write_metro_pdf(graph, metro_path)

    print(json.dumps(
        {
            "ok": True,
            "graph": str(graph_path),
            "outputs": {
                "sankey_html": str(sankey_path),
                "frontier_pdf": str(frontier_path),
                "metro_pdf": str(metro_path),
            },
        },
        indent=2,
        ensure_ascii=False,
    ))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
