from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.action_policy import ActionKind, classify_actions
from ui_explorer.core.actions import extract_actions, summarize_actions
from ui_explorer.core.a11y_parser import parse_a11y_xml


def main() -> int:
    parser = argparse.ArgumentParser(description="List actionable visible controls from active root.")
    parser.add_argument("xml", type=Path)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--kind",
        choices=[item.value for item in ActionKind],
        default=None,
        help="Filter by classified action kind.",
    )
    args = parser.parse_args()

    root = parse_a11y_xml(args.xml)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    classified = classify_actions(actions)

    if args.kind:
        classified = [item for item in classified if item.kind.value == args.kind]

    kind_counts: dict[str, int] = {}
    for item in classified:
        kind_counts[item.kind.value] = kind_counts.get(item.kind.value, 0) + 1

    result = {
        "active_root": {
            "kind": active.kind,
            "reason": active.reason,
            "role": active.node.role,
            "name": active.node.name,
            "bbox": active.node.bbox.as_list(),
        },
        "action_count": len(actions),
        "raw_role_counts": summarize_actions(actions),
        "shown_count": len(classified),
        "kind_counts": dict(sorted(kind_counts.items())),
        "actions": [item.to_dict() for item in classified[: args.limit]],
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
