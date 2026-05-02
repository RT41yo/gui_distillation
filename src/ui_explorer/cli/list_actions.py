from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.actions import extract_actions, summarize_actions
from ui_explorer.core.a11y_parser import parse_a11y_xml


def main() -> int:
    parser = argparse.ArgumentParser(description="List actionable visible controls from active root.")
    parser.add_argument("xml", type=Path)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    root = parse_a11y_xml(args.xml)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)

    result = {
        "active_root": {
            "kind": active.kind,
            "reason": active.reason,
            "role": active.node.role,
            "name": active.node.name,
            "bbox": active.node.bbox.as_list(),
        },
        "action_count": len(actions),
        "role_counts": summarize_actions(actions),
        "actions": [a.to_dict() for a in actions[: args.limit]],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
