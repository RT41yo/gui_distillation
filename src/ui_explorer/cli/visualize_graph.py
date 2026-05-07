from __future__ import annotations

import argparse
import json
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch


STATUS_STYLE = {
    "confirmed": {
        "color": "#1f77b4",
        "linewidth": 1.7,
        "linestyle": "-",
        "alpha": 0.88,
    },
    "pending": {
        "color": "#8a8a8a",
        "linewidth": 0.9,
        "linestyle": "--",
        "alpha": 0.42,
    },
    "same_state": {
        "color": "#9467bd",
        "linewidth": 1.1,
        "linestyle": ":",
        "alpha": 0.75,
    },
    "content_changed": {
        "color": "#ff7f0e",
        "linewidth": 1.2,
        "linestyle": "-.",
        "alpha": 0.78,
    },
    "focus_changed": {
        "color": "#17becf",
        "linewidth": 1.1,
        "linestyle": "-.",
        "alpha": 0.75,
    },
    "selection_changed": {
        "color": "#bcbd22",
        "linewidth": 1.1,
        "linestyle": "-.",
        "alpha": 0.75,
    },
    "failed_click": {
        "color": "#d62728",
        "linewidth": 1.1,
        "linestyle": ":",
        "alpha": 0.78,
    },
    "failed_navigation": {
        "color": "#d62728",
        "linewidth": 1.1,
        "linestyle": "--",
        "alpha": 0.78,
    },
    "blocked_by_modal": {
        "color": "#d62728",
        "linewidth": 1.1,
        "linestyle": "-.",
        "alpha": 0.78,
    },
    "skipped_policy": {
        "color": "#aaaaaa",
        "linewidth": 0.9,
        "linestyle": ":",
        "alpha": 0.65,
    },
    "skipped_depth": {
        "color": "#aaaaaa",
        "linewidth": 0.9,
        "linestyle": ":",
        "alpha": 0.65,
    },
    "external": {
        "color": "#7f7f7f",
        "linewidth": 1.0,
        "linestyle": "--",
        "alpha": 0.7,
    },
    "requires_input": {
        "color": "#e377c2",
        "linewidth": 1.0,
        "linestyle": "--",
        "alpha": 0.75,
    },
}


NODE_KIND_STYLE = {
    "main": {
        "facecolor": "#e8f1fb",
        "edgecolor": "#1f77b4",
    },
    "menu": {
        "facecolor": "#fff3d6",
        "edgecolor": "#d99a00",
    },
    "dialog": {
        "facecolor": "#f7e6ff",
        "edgecolor": "#7b3294",
    },
    "alert": {
        "facecolor": "#ffe6e6",
        "edgecolor": "#d62728",
    },
    "window_overlay": {
        "facecolor": "#e8f7ef",
        "edgecolor": "#2ca25f",
    },
    "secondary_frame": {
        "facecolor": "#eeeeee",
        "edgecolor": "#555555",
    },
    "unknown": {
        "facecolor": "#f5f5f5",
        "edgecolor": "#777777",
    },
}


def load_graph(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"graph.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def node_kind(node: dict[str, Any]) -> str:
    return node.get("active_root", {}).get("kind") or "unknown"


def node_label(
    state_id: str,
    node: dict[str, Any],
    root_state_id: str,
    pending_count: int = 0,
) -> str:
    label = (
        node.get("label")
        or node.get("active_root", {}).get("name")
        or node.get("active_root", {}).get("role")
        or "state"
    )

    kind = node_kind(node)
    depth = node.get("depth", "?")
    macro_count = node.get("macro_action_count", "?")

    root_mark = "ROOT\n" if state_id == root_state_id else ""
    pending_line = f"\npending={pending_count}" if pending_count else ""

    raw = (
        f"{root_mark}{label}\n"
        f"{state_id}\n"
        f"kind={kind}, d={depth}, a={macro_count}"
        f"{pending_line}"
    )

    lines: list[str] = []
    for line in raw.splitlines():
        lines.extend(textwrap.wrap(line, width=30) or [""])
    return "\n".join(lines)


def edge_label(edge: dict[str, Any]) -> str:
    action = edge.get("action", {})
    name = action.get("name") or action.get("role") or "action"
    status = edge.get("status", "")

    short = textwrap.shorten(str(name), width=24, placeholder="…")

    if status == "confirmed":
        return short

    return f"{short}\n[{status}]"


def layered_positions(data: dict[str, Any]) -> dict[str, tuple[float, float]]:
    layers: dict[int, list[str]] = defaultdict(list)

    for state_id, node in data.get("nodes", {}).items():
        layers[int(node.get("depth", 0))].append(state_id)

    for depth in layers:
        layers[depth].sort(
            key=lambda sid: (
                data["nodes"][sid].get("label") or "",
                node_kind(data["nodes"][sid]),
                sid,
            )
        )

    pos: dict[str, tuple[float, float]] = {}

    x_gap = 5.0
    y_gap = 2.55

    for depth in sorted(layers):
        states = layers[depth]
        n = len(states)

        for i, state_id in enumerate(states):
            x = depth * x_gap
            y = ((n - 1) / 2 - i) * y_gap
            pos[state_id] = (x, y)

    return pos


def draw_node(
    ax,
    x: float,
    y: float,
    label: str,
    kind: str,
    is_root: bool,
) -> None:
    style = NODE_KIND_STYLE.get(kind, NODE_KIND_STYLE["unknown"])

    bbox = dict(
        boxstyle="round,pad=0.58,rounding_size=0.18",
        facecolor=style["facecolor"],
        edgecolor="#111111" if is_root else style["edgecolor"],
        linewidth=2.35 if is_root else 1.35,
        alpha=0.98,
    )

    ax.text(
        x,
        y,
        label,
        ha="center",
        va="center",
        fontsize=8.2,
        family="DejaVu Sans",
        bbox=bbox,
        zorder=5,
    )


def draw_edge(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    status: str,
    label: str,
    curvature: float,
) -> None:
    style = STATUS_STYLE.get(
        status,
        {
            "color": "#666666",
            "linewidth": 1.0,
            "linestyle": "-",
            "alpha": 0.65,
        },
    )

    x1, y1 = start
    x2, y2 = end

    if start == end:
        loop = FancyArrowPatch(
            (x1 + 0.35, y1 + 0.62),
            (x1 + 0.35, y1 + 0.62),
            connectionstyle="arc3,rad=1.75",
            arrowstyle="-|>",
            mutation_scale=9,
            color=style["color"],
            linewidth=style["linewidth"],
            linestyle=style["linestyle"],
            alpha=style["alpha"],
            zorder=2,
        )
        ax.add_patch(loop)

        ax.text(
            x1 + 0.95,
            y1 + 0.9,
            label,
            fontsize=6.4,
            color=style["color"],
            ha="left",
            va="center",
            alpha=0.9,
            bbox=dict(
                boxstyle="round,pad=0.15",
                facecolor="white",
                edgecolor="none",
                alpha=0.68,
            ),
            zorder=4,
        )
        return

    arrow = FancyArrowPatch(
        (x1 + 1.25, y1),
        (x2 - 1.25, y2),
        connectionstyle=f"arc3,rad={curvature}",
        arrowstyle="-|>",
        mutation_scale=10,
        color=style["color"],
        linewidth=style["linewidth"],
        linestyle=style["linestyle"],
        alpha=style["alpha"],
        zorder=1,
    )
    ax.add_patch(arrow)

    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2 + curvature * 1.35

    ax.text(
        mx,
        my,
        label,
        fontsize=6.2,
        color=style["color"],
        ha="center",
        va="center",
        alpha=0.92,
        bbox=dict(
            boxstyle="round,pad=0.18",
            facecolor="white",
            edgecolor="none",
            alpha=0.74,
        ),
        zorder=4,
    )


def add_legend(ax, show_pending: bool) -> None:
    pending_line = (
        "pending — dashed self/unknown edges"
        if show_pending
        else "pending edges are summarized inside nodes"
    )

    lines = [
        "Legend",
        "",
        "Node kind:",
        "main · menu · dialog · window_overlay",
        "",
        "Edge status:",
        "confirmed — solid",
        pending_line,
        "content/same/failed — styled",
    ]

    ax.text(
        0.012,
        0.012,
        "\n".join(lines),
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.2,
        family="DejaVu Sans",
        bbox=dict(
            boxstyle="round,pad=0.45",
            facecolor="#ffffff",
            edgecolor="#dddddd",
            alpha=0.94,
        ),
    )


def add_summary_page(
    pdf: PdfPages,
    data: dict[str, Any],
    depth_counts: dict[int, int],
    status_counts: dict[str, int],
    pending_by_state: dict[str, int],
) -> None:
    root_state_id = data.get("root_state_id")

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")
    fig.patch.set_facecolor("white")

    summary_lines = [
        "A11Y UI Exploration Graph Summary",
        "",
        f"Application: {data.get('app_id')}",
        f"Root state: {root_state_id}",
        f"Schema version: {data.get('schema_version')}",
        "",
        "Depth distribution:",
        *[f"  depth {d}: {depth_counts[d]} node(s)" for d in sorted(depth_counts)],
        "",
        "Edge status distribution:",
        *[f"  {k}: {v}" for k, v in sorted(status_counts.items())],
        "",
        "Pending frontier by state:",
    ]

    if pending_by_state:
        nodes = data.get("nodes", {})
        for state_id, count in sorted(
            pending_by_state.items(),
            key=lambda item: (
                nodes.get(item[0], {}).get("depth", 0),
                nodes.get(item[0], {}).get("label") or "",
                item[0],
            ),
        ):
            node = nodes.get(state_id, {})
            label = (
                node.get("label")
                or node.get("active_root", {}).get("name")
                or node.get("active_root", {}).get("role")
                or "state"
            )
            depth = node.get("depth", "?")
            kind = node_kind(node)
            summary_lines.append(
                f"  {state_id}  depth={depth}  kind={kind}  pending={count}  label={label}"
            )
    else:
        summary_lines.append("  none")

    summary_lines.extend(
        [
            "",
            "Completion:",
            *[f"  {k}: {v}" for k, v in data.get("completion", {}).items()],
        ]
    )

    ax.text(
        0.055,
        0.945,
        "\n".join(summary_lines),
        ha="left",
        va="top",
        fontsize=10.2,
        family="DejaVu Sans Mono",
        bbox=dict(
            boxstyle="round,pad=0.8",
            facecolor="#fafafa",
            edgecolor="#dddddd",
        ),
    )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def add_pending_actions_page(
    pdf: PdfPages,
    data: dict[str, Any],
) -> None:
    edges = data.get("edges", {})
    nodes = data.get("nodes", {})

    pending_edges = [
        edge
        for edge in edges.values()
        if edge.get("status") == "pending"
    ]

    pending_edges.sort(
        key=lambda edge: (
            nodes.get(edge["from_state"], {}).get("depth", 0),
            edge.get("priority", 50),
            edge.get("created_order", 0),
        )
    )

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.axis("off")
    fig.patch.set_facecolor("white")

    lines = [
        "Pending Edge Details",
        "",
    ]

    if not pending_edges:
        lines.append("No pending edges.")
    else:
        for edge in pending_edges[:55]:
            from_state = edge.get("from_state")
            from_node = nodes.get(from_state, {})
            action = edge.get("action", {})
            action_name = action.get("name") or action.get("role") or "action"

            lines.append(
                f"- depth={from_node.get('depth', '?')} "
                f"from={from_state} "
                f"priority={edge.get('priority')} "
                f"action={action_name}"
            )

        if len(pending_edges) > 55:
            lines.append("")
            lines.append(f"... truncated: {len(pending_edges) - 55} more pending edges")

    ax.text(
        0.055,
        0.945,
        "\n".join(lines),
        ha="left",
        va="top",
        fontsize=9.4,
        family="DejaVu Sans Mono",
        bbox=dict(
            boxstyle="round,pad=0.8",
            facecolor="#fafafa",
            edgecolor="#dddddd",
        ),
    )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def visualize_graph(
    graph_json: Path,
    output_pdf: Path,
    title: str | None = None,
    show_pending: bool = False,
) -> Path:
    data = load_graph(graph_json)

    nodes = data.get("nodes", {})
    edges = data.get("edges", {})
    root_state_id = data.get("root_state_id")

    pos = layered_positions(data)

    depth_counts: dict[int, int] = defaultdict(int)
    for node in nodes.values():
        depth_counts[int(node.get("depth", 0))] += 1

    status_counts: dict[str, int] = defaultdict(int)
    for edge in edges.values():
        status_counts[edge.get("status", "unknown")] += 1

    pending_by_state: dict[str, int] = defaultdict(int)
    for edge in edges.values():
        if edge.get("status") == "pending":
            pending_by_state[edge["from_state"]] += 1

    max_depth = max(depth_counts.keys(), default=0)
    max_layer_size = max(depth_counts.values(), default=1)

    width = max(11.0, 5.5 + max_depth * 4.4)
    height = max(8.0, 3.2 + max_layer_size * 1.58)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(output_pdf) as pdf:
        fig, ax = plt.subplots(figsize=(width, height))
        ax.set_facecolor("#fbfbfc")
        fig.patch.set_facecolor("white")

        xs = [p[0] for p in pos.values()] or [0.0]
        ys = [p[1] for p in pos.values()] or [0.0]

        ax.set_xlim(min(xs) - 3.2, max(xs) + 3.2)
        ax.set_ylim(min(ys) - 2.7, max(ys) + 2.7)

        y_top = max(ys) + 2.35

        for depth in range(max_depth + 1):
            x = depth * 5.0
            ax.axvline(x=x, color="#e7e7e7", linewidth=0.9, zorder=0)
            ax.text(
                x,
                y_top,
                f"depth {depth}",
                ha="center",
                va="bottom",
                fontsize=8.3,
                color="#666666",
            )

        pair_index: dict[tuple[str, str], int] = defaultdict(int)

        for _, edge in edges.items():
            status = edge.get("status", "unknown")

            # Important readability rule:
            # pending edges usually have to_state=null, so drawing all of them
            # creates many overlapping self-loop labels near the same node.
            if status == "pending" and not show_pending:
                continue

            u = edge["from_state"]
            v = edge.get("to_state") or u

            if u not in pos:
                continue

            if v not in pos:
                v = u

            pair = (u, v)
            idx = pair_index[pair]
            pair_index[pair] += 1

            curvature = 0.0
            if u == v:
                curvature = 1.2
            elif idx:
                curvature = 0.12 * ((idx + 1) // 2) * (1 if idx % 2 else -1)

            draw_edge(
                ax=ax,
                start=pos[u],
                end=pos[v],
                status=status,
                label=edge_label(edge),
                curvature=curvature,
            )

        for state_id, node in nodes.items():
            x, y = pos[state_id]
            kind = node_kind(node)

            draw_node(
                ax=ax,
                x=x,
                y=y,
                label=node_label(
                    state_id=state_id,
                    node=node,
                    root_state_id=root_state_id,
                    pending_count=pending_by_state.get(state_id, 0),
                ),
                kind=kind,
                is_root=state_id == root_state_id,
            )

        title_text = title or f"A11Y UI Exploration Graph: {data.get('app_id', 'app')}"
        subtitle = (
            f"nodes={len(nodes)} · edges={len(edges)} · "
            f"pending={status_counts.get('pending', 0)} · "
            f"confirmed={status_counts.get('confirmed', 0)} · "
            f"root={root_state_id}"
        )

        fig.suptitle(title_text, fontsize=15, fontweight="bold", y=0.985)
        ax.set_title(subtitle, fontsize=9.5, color="#444444", pad=18)

        add_legend(ax, show_pending=show_pending)

        ax.axis("off")
        plt.tight_layout(rect=[0, 0, 1, 0.95])
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        add_summary_page(
            pdf=pdf,
            data=data,
            depth_counts=depth_counts,
            status_counts=status_counts,
            pending_by_state=pending_by_state,
        )

        add_pending_actions_page(
            pdf=pdf,
            data=data,
        )

    return output_pdf


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Visualize UI Explorer graph.json as a scientific layered PDF."
    )
    parser.add_argument("--app", default="calc")
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--graph", default=None, help="Explicit path to graph.json")
    parser.add_argument("-o", "--output", default=None, help="Output PDF path")
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--show-pending",
        action="store_true",
        help=(
            "Draw pending edges on the main graph. "
            "By default pending edges are summarized inside nodes."
        ),
    )

    args = parser.parse_args()

    graph_json = (
        Path(args.graph)
        if args.graph
        else Path(args.maps) / args.app / "graph.json"
    )

    output_pdf = (
        Path(args.output)
        if args.output
        else Path(args.maps) / args.app / "graph.pdf"
    )

    saved = visualize_graph(
        graph_json=graph_json,
        output_pdf=output_pdf,
        title=args.title,
        show_pending=args.show_pending,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "graph_json": str(graph_json),
                "output": str(saved),
                "show_pending": args.show_pending,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
