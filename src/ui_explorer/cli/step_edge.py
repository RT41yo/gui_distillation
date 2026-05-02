from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from ui_explorer.app.launcher import AppLauncher
from ui_explorer.app.registry import AppRegistry
from ui_explorer.core.diff import DiffClassifier
from ui_explorer.execution.executor import ActionExecutor
from ui_explorer.execution.wait import A11YWaiter
from ui_explorer.graph.scheduler import BFSScheduler, SchedulerPolicy
from ui_explorer.graph.store import GraphStore
from ui_explorer.execution.navigator import Navigator
from ui_explorer.graph.models import EdgeStatus


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute next pending edge and update graph.")
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

    tmp_dir = Path(args.maps) / args.app / "_tmp" / "step_edge"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    waiter = A11YWaiter(a11y_name=app_cfg.a11y_name)

    # Step 12 MVP: if the selected edge starts from root, reset to root first.
    # For non-root edges replay-path navigation will be added later.
    if edge.from_state == graph.root_state_id:
        nav_result, nav_state = Navigator(
            a11y_name=app_cfg.a11y_name,
            display=args.display,
        ).reset_to_root(
            root_state_id=graph.root_state_id,
            output_dir=tmp_dir / "reset",
        )

        if not nav_result.ok or nav_state is None:
            edge.attempts += 1
            edge.status = EdgeStatus.FAILED_NAVIGATION
            edge.reason = nav_result.reason
            edge.observed = {"navigation": nav_result.to_dict()}
            store.save(graph)
            print(json.dumps(
                {
                    "ok": False,
                    "error": "reset_to_root failed",
                    "navigation": nav_result.to_dict(),
                    "edge_status": edge.status.value,
                },
                indent=2,
                ensure_ascii=False,
            ))
            return 2

        before = nav_state
    else:
        before = waiter.capture_once(tmp_dir / "before.xml")

        if before.signature.state_id != edge.from_state:
            edge.attempts += 1
            edge.status = EdgeStatus.FAILED_NAVIGATION
            edge.reason = (
                f"live state mismatch: expected {edge.from_state}, "
                f"got {before.signature.state_id}"
            )
            edge.observed = {
                "navigation": {
                    "ok": False,
                    "reason": "replay path navigation not implemented yet",
                    "expected_from_state": edge.from_state,
                    "actual_state": before.signature.state_id,
                }
            }
            store.save(graph)
            print(json.dumps(
                {
                    "ok": False,
                    "error": "current live state does not match edge.from_state",
                    "expected_from_state": edge.from_state,
                    "actual_state": before.signature.state_id,
                    "edge_status": edge.status.value,
                    "hint": "Replay path navigation for non-root edges will be added in the next step.",
                },
                indent=2,
                ensure_ascii=False,
            ))
            return 2

    execution = ActionExecutor(
        display=args.display,
        window_name=app_cfg.display_name,
    ).click_bbox(edge.action["bbox"])
    after = waiter.capture_stable(tmp_dir, "after")

    transition = DiffClassifier().classify(
        before=before.signature,
        after=after.signature,
        execution=execution,
    )

    store.apply_transition(
        graph=graph,
        edge_id_value=edge.edge_id,
        after_xml_path=after.xml_path,
        transition=transition,
    )
    graph_path = store.save(graph)

    status_counts: dict[str, int] = {}
    for e in graph.edges.values():
        status_counts[e.status.value] = status_counts.get(e.status.value, 0) + 1

    print(json.dumps(
        {
            "ok": execution.ok,
            "graph_path": str(graph_path),
            "executed_edge": edge.edge_id,
            "executed_action": {
                "role": edge.action.get("role"),
                "name": edge.action.get("name"),
                "action_key": edge.action_key,
            },
            "execution": execution.to_dict(),
            "transition": transition.to_dict(),
            "before_state": before.signature.state_id,
            "after_state": after.signature.state_id,
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "edge_status_counts": dict(sorted(status_counts.items())),
            "completion": graph.completion,
            "after_xml": str(after.xml_path),
        },
        indent=2,
        ensure_ascii=False,
    ))

    return 0 if execution.ok else 1


if __name__ == "__main__":
    sys.exit(main())
