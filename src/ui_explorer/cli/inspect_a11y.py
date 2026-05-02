from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.core.a11y_parser import parse_a11y_xml, role_counts, visible_nodes, walk


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect captured A11Y XML.")
    parser.add_argument("xml", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    root = parse_a11y_xml(args.xml)
    all_nodes = list(walk(root))
    vis_nodes = visible_nodes(root)

    print(f"root: {root.label}")
    print(f"all_nodes: {len(all_nodes)}")
    print(f"visible_nodes: {len(vis_nodes)}")
    print("visible_role_counts:")
    print(json.dumps(role_counts(vis_nodes), indent=2, ensure_ascii=False))

    print("sample_visible_nodes:")
    for node in vis_nodes[: args.limit]:
        print(
            json.dumps(
                {
                    "role": node.role,
                    "name": node.name,
                    "states": list(node.states),
                    "bbox": node.bbox.as_list(),
                    "parent_path": list(node.parent_path),
                },
                ensure_ascii=False,
            )
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
