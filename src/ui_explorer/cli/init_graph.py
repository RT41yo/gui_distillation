from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ui_explorer.core.screenshot import save_screenshot
from ui_explorer.graph.store import GraphStore


def _state_screenshot_path(
    *,
    maps_dir: str,
    app_id: str,
    state_id: str,
) -> Path:
    return (
        Path(maps_dir)
        / app_id
        / "states"
        / state_id
        / "screenshot.png"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize exploration graph from captured A11Y XML.")
    parser.add_argument("--app", required=True)
    parser.add_argument("--xml", required=True, type=Path)
    parser.add_argument("--output", default="data/maps")
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":99"))
    args = parser.parse_args()

    store = GraphStore(Path(args.output))
    graph = store.init_from_xml(app_id=args.app, xml_path=args.xml)
    path = store.graph_path(args.app)

    root_screenshot_path = _state_screenshot_path(
        maps_dir=args.output,
        app_id=args.app,
        state_id=graph.root_state_id,
    )

    root_screenshot_saved = save_screenshot(
        root_screenshot_path,
        display=args.display,
        overwrite=False,
    )

    pending = sum(1 for edge in graph.edges.values() if edge.status.value == "pending")

    print(json.dumps(
        {
            "graph_path": str(path),
            "root_state_id": graph.root_state_id,
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "pending_edges": pending,
            "root_screenshot": {
                "saved": root_screenshot_saved,
                "path": str(root_screenshot_path),
            },
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
