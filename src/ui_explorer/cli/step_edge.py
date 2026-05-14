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
from ui_explorer.execution.navigator import Navigator
from ui_explorer.execution.wait import A11YWaiter
from ui_explorer.graph.models import EdgeStatus
from ui_explorer.graph.scheduler import BFSScheduler, SchedulerPolicy
from ui_explorer.graph.store import GraphStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute next pending edge and update graph."
    )

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
        AppLauncher().launch(
            app_cfg.launcher,
            display=args.display,
        )

    store = GraphStore(Path(args.maps))
    graph = store.load(args.app)

    edge = BFSScheduler(
        SchedulerPolicy(max_depth=args.max_depth)
    ).next_edge(graph)

    if edge is None:
        print(json.dumps(
            {"ok": False, "error": "no pending edge"},
            indent=2,
        ))
        return 1

    tmp_dir = (
        Path(args.maps)
        / args.app
        / "_tmp"
        / "step_edge"
    )

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    tmp_dir.mkdir(parents=True, exist_ok=True)

    waiter = A11YWaiter(a11y_name=app_cfg.a11y_name)

    navigator = Navigator(
        a11y_name=app_cfg.a11y_name,
        display=args.display,
        graph_store=store,
        window_name=app_cfg.display_name,
    )

    navigation_dir = tmp_dir / "navigation"
    navigation_dir.mkdir(parents=True, exist_ok=True)

    nav_result, before = navigator.navigate_to_state(
        graph=graph,
        target_state_id=edge.from_state,
        output_dir=navigation_dir,
    )

    if not nav_result.ok or before is None:
        edge.attempts += 1
        edge.status = EdgeStatus.FAILED_NAVIGATION
        edge.reason = nav_result.reason
        edge.observed = {
            "navigation": nav_result.to_dict(),
        }

        store.save(graph)

        print(json.dumps(
            {
                "ok": False,
                "error": "navigation failed",
                "navigation": nav_result.to_dict(),
                "edge_status": edge.status.value,
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
        status_counts[e.status.value] = (
            status_counts.get(e.status.value, 0) + 1
        )

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
            "navigation": nav_result.to_dict(),
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
