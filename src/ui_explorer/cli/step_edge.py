from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

import os
import signal

from ui_explorer.app.launcher import AppLauncher
from ui_explorer.app.registry import AppRegistry
from ui_explorer.core.diff import DiffClassifier
from ui_explorer.execution.executor import ActionExecutor
from ui_explorer.execution.navigator import Navigator
from ui_explorer.execution.wait import A11YWaiter
from ui_explorer.graph.models import EdgeStatus
from ui_explorer.graph.scheduler import BFSScheduler, SchedulerPolicy
from ui_explorer.graph.store import GraphStore


def _launcher_binary(launcher: list[str] | str) -> str:
    """
    Extract executable basename from app launcher config.
    """
    if isinstance(launcher, str):
        binary = launcher.split()[0]
    else:
        if not launcher:
            raise ValueError("empty launcher")
        binary = str(launcher[0])

    return Path(binary).name


def _terminate_app(launcher: list[str] | str) -> None:
    """
    Generic best-effort process termination by launcher command line.

    We intentionally avoid plain `pkill -f <binary>` because for apps like
    Nautilus the current command line contains `--app nautilus`, so it may kill
    this step_edge process.

    We also avoid only `pkill -x` because long process names such as
    gnome-calculator may be truncated in Linux comm.
    """

    binary = _launcher_binary(launcher)
    current_pid = os.getpid()

    try:
        result = subprocess.run(
            ["pgrep", "-f", binary],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                pid = int(line)
            except ValueError:
                continue

            if pid == current_pid:
                continue

            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception:
                logging.exception("Failed to terminate pid=%s", pid)

    except Exception:
        logging.exception("App termination failed")

    time.sleep(0.7)


def _hard_reset_app(
    *,
    launcher: list[str] | str,
    display: str,
    wait_s: float,
) -> None:
    """
    Restart app from a clean process baseline.
    """
    logging.info("Hard reset app via relaunch")
    _terminate_app(launcher)
    AppLauncher().launch(launcher, display=display)
    time.sleep(wait_s)


def _make_navigator(
    *,
    app_cfg,
    display: str,
    store: GraphStore,
) -> Navigator:
    return Navigator(
        a11y_name=app_cfg.a11y_name,
        display=display,
        graph_store=store,
        window_name=app_cfg.display_name,
    )


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
    parser.add_argument(
        "--navigation",
        choices=["hard", "soft"],
        default="hard",
        help=(
            "Navigation strategy before executing an edge. "
            "hard = relaunch app before every edge; "
            "soft = try current-state navigation first, then hard fallback."
        ),
    )
    parser.add_argument(
        "--hard-reset-wait",
        type=float,
        default=3.0,
        help="Seconds to wait after hard app relaunch.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    app_cfg = AppRegistry(Path(args.apps_config)).get(args.app)

    if args.launch and args.navigation == "soft":
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

    navigation_dir = tmp_dir / "navigation"
    navigation_dir.mkdir(parents=True, exist_ok=True)

    if args.navigation == "hard":
        _hard_reset_app(
            launcher=app_cfg.launcher,
            display=args.display,
            wait_s=args.hard_reset_wait,
        )

    navigator = _make_navigator(
        app_cfg=app_cfg,
        display=args.display,
        store=store,
    )

    nav_result, before = navigator.navigate_to_state(
        graph=graph,
        target_state_id=edge.from_state,
        output_dir=navigation_dir,
    )

    # In soft mode, keep old behavior first. If it fails, retry once from a
    # clean app process baseline. In hard mode this retry is unnecessary
    # because the app was already relaunched before navigation.
    if (not nav_result.ok or before is None) and args.navigation == "soft":
        logging.warning(
            "Soft navigation failed; trying hard reset fallback: %s",
            nav_result.reason,
        )

        _hard_reset_app(
            launcher=app_cfg.launcher,
            display=args.display,
            wait_s=args.hard_reset_wait,
        )

        navigator = _make_navigator(
            app_cfg=app_cfg,
            display=args.display,
            store=store,
        )

        nav_result, before = navigator.navigate_to_state(
            graph=graph,
            target_state_id=edge.from_state,
            output_dir=navigation_dir / "after_hard_reset",
        )

    if not nav_result.ok or before is None:
        edge.attempts += 1
        edge.status = EdgeStatus.FAILED_NAVIGATION
        edge.reason = nav_result.reason
        edge.observed = {
            "navigation_strategy": args.navigation,
            "navigation": nav_result.to_dict(),
        }

        store.save(graph)

        print(json.dumps(
            {
                "ok": False,
                "error": "navigation failed",
                "navigation_strategy": args.navigation,
                "selected_edge": edge.edge_id,
                "selected_from_state": edge.from_state,
                "selected_action": {
                    "role": edge.action.get("role"),
                    "name": edge.action.get("name"),
                    "action_key": edge.action_key,
                },
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
            "navigation_strategy": args.navigation,
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
