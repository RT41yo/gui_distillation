from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.graph.scheduler import BFSScheduler, SchedulerPolicy
from ui_explorer.graph.store import GraphStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Show next pending edge selected by scheduler.")
    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--max-depth", type=int, default=5)
    args = parser.parse_args()

    graph = GraphStore(Path(args.maps)).load(args.app)
    edge = BFSScheduler(SchedulerPolicy(max_depth=args.max_depth)).next_edge(graph)

    if edge is None:
        print(json.dumps({"next_edge": None}, indent=2))
        return 0

    from_node = graph.nodes[edge.from_state]
    print(json.dumps(
        {
            "next_edge": {
                "edge_id": edge.edge_id,
                "from_state": edge.from_state,
                "from_depth": from_node.depth,
                "to_state": edge.to_state,
                "status": edge.status.value,
                "priority": edge.priority,
                "attempts": edge.attempts,
                "created_order": edge.created_order,
                "reason": edge.reason,
                "action": edge.action,
            }
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
