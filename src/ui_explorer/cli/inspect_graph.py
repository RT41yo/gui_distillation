from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from ui_explorer.graph.models import EdgeStatus
from ui_explorer.graph.store import GraphStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect exploration graph.")
    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    args = parser.parse_args()

    graph = GraphStore(Path(args.maps)).load(args.app)

    edge_status_counts = Counter(edge.status.value for edge in graph.edges.values())
    node_depth_counts = Counter(node.depth for node in graph.nodes.values())

    pending = [
        edge
        for edge in graph.edges.values()
        if edge.status == EdgeStatus.PENDING
    ]

    pending_sorted = sorted(
        pending,
        key=lambda edge: (
            graph.nodes[edge.from_state].depth,
            edge.priority,
            edge.attempts,
            edge.created_order,
        ),
    )

    result = {
        "app_id": graph.app_id,
        "root_state_id": graph.root_state_id,
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "completion": graph.completion,
        "node_depth_counts": dict(sorted(node_depth_counts.items())),
        "edge_status_counts": dict(sorted(edge_status_counts.items())),
        "next_pending_preview": [
            {
                "edge_id": edge.edge_id,
                "from_state": edge.from_state,
                "from_depth": graph.nodes[edge.from_state].depth,
                "action": {
                    "role": edge.action.get("role"),
                    "name": edge.action.get("name"),
                    "action_key": edge.action_key,
                },
                "priority": edge.priority,
                "attempts": edge.attempts,
                "created_order": edge.created_order,
                "reason": edge.reason,
            }
            for edge in pending_sorted[:10]
        ],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
