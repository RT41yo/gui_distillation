from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.graph.store import GraphStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize exploration graph from captured A11Y XML.")
    parser.add_argument("--app", required=True)
    parser.add_argument("--xml", required=True, type=Path)
    parser.add_argument("--output", default="data/maps")
    args = parser.parse_args()

    store = GraphStore(Path(args.output))
    graph = store.init_from_xml(app_id=args.app, xml_path=args.xml)
    path = store.graph_path(args.app)

    pending = sum(1 for edge in graph.edges.values() if edge.status.value == "pending")

    print(json.dumps(
        {
            "graph_path": str(path),
            "root_state_id": graph.root_state_id,
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "pending_edges": pending,
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
