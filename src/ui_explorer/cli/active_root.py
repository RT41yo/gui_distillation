from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.a11y_parser import parse_a11y_xml


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve active interaction root for A11Y XML.")
    parser.add_argument("xml", type=Path)
    args = parser.parse_args()

    root = parse_a11y_xml(args.xml)
    active = resolve_active_root(root)

    print(json.dumps(
        {
            "kind": active.kind,
            "reason": active.reason,
            "role": active.node.role,
            "name": active.node.name,
            "bbox": active.node.bbox.as_list(),
            "parent_path": list(active.node.parent_path),
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
