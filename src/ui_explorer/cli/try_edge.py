from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from ui_explorer.app.launcher import AppLauncher
from ui_explorer.app.registry import AppRegistry
from ui_explorer.execution.executor import ActionExecutor
from ui_explorer.execution.wait import A11YWaiter
from ui_explorer.graph.scheduler import BFSScheduler, SchedulerPolicy
from ui_explorer.graph.store import GraphStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Try executing the next pending edge without updating graph.")
    parser.add_argument("--app", required=True)
    parser.add_argument("--display", default=":99")
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--apps-config", default="config/apps.yaml")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    app_cfg = AppRegistry(Path(args.apps_config)).get(args.app)

    if args.launch:
        AppLauncher().launch(app_cfg.launcher, display=args.display)

    store = GraphStore(Path(args.maps))
    graph = store.load(args.app)

    edge = BFSScheduler(SchedulerPolicy(max_depth=args.max_depth)).next_edge(graph)
    if edge is None:
        print(json.dumps({"ok": False, "error": "no pending edge"}, indent=2))
        return 1

    tmp_dir = Path(args.maps) / args.app / "_tmp" / "try_edge"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    waiter = A11YWaiter(a11y_name=app_cfg.a11y_name)

    before = waiter.capture_once(tmp_dir / "before.xml")

    if before.signature.state_id != edge.from_state:
        print(json.dumps(
            {
                "ok": False,
                "error": "current live state does not match edge.from_state",
                "expected_from_state": edge.from_state,
                "actual_state": before.signature.state_id,
                "before_xml": str(before.xml_path),
                "hint": "For now Step 10 only supports trying root/current-state edges. Navigation comes later.",
            },
            indent=2,
            ensure_ascii=False,
        ))
        return 2

    execution = ActionExecutor(display=args.display).click_bbox(edge.action["bbox"])
    after = waiter.capture_stable(tmp_dir, "after")

    result = {
        "ok": execution.ok,
        "executed_edge": edge.edge_id,
        "executed_action": {
            "role": edge.action.get("role"),
            "name": edge.action.get("name"),
            "action_key": edge.action_key,
            "bbox": edge.action.get("bbox"),
        },
        "execution": execution.to_dict(),
        "before_state": before.signature.state_id,
        "after_state": after.signature.state_id,
        "macro_changed": before.signature.macro_hash != after.signature.macro_hash,
        "content_changed": before.signature.content_hash != after.signature.content_hash,
        "before_xml": str(before.xml_path),
        "after_xml": str(after.xml_path),
        "after_signature": after.signature.to_dict(),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if execution.ok else 1


if __name__ == "__main__":
    sys.exit(main())
