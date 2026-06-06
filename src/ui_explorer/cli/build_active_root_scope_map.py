from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ui_explorer.core.action_policy import ActionKind, classify_actions
from ui_explorer.core.actions import extract_actions
from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.a11y_parser import parse_a11y_xml
from ui_explorer.graph.models import ExplorationGraph, StateNode
from ui_explorer.graph.store import GraphStore


def _state_xml_path(node: StateNode, maps_dir: Path, app_id: str) -> Path:
    xml_path = Path(node.xml_path)

    if xml_path.exists():
        return xml_path

    return maps_dir / app_id / "states" / node.state_id / "a11y.xml"


def _state_screenshot_path(
    node: StateNode,
    maps_dir: Path,
    app_id: str,
) -> Path | None:
    path = maps_dir / app_id / "states" / node.state_id / "screenshot.png"

    if path.exists():
        return path

    return None


def _active_root_payload(active) -> dict[str, Any]:
    return {
        "kind": active.kind,
        "reason": active.reason,
        "role": active.node.role,
        "name": active.node.name,
        "description": active.node.description,
        "states": list(active.node.states),
        "bbox_visible": active.node.is_visible,
        "parent_path": list(active.node.parent_path),
    }


def _graph_active_root_matches(
    graph_active_root: dict[str, Any],
    recomputed_active_root: dict[str, Any],
) -> bool:
    for key in ("kind", "role", "name"):
        if (graph_active_root.get(key) or "") != (recomputed_active_root.get(key) or ""):
            return False

    graph_parent_path = list(graph_active_root.get("parent_path") or [])
    recomputed_parent_path = list(recomputed_active_root.get("parent_path") or [])

    return graph_parent_path == recomputed_parent_path


def _bbox_valid(bbox: list[int] | tuple[int, int, int, int]) -> bool:
    x, y, width, height = bbox
    return x >= 0 and y >= 0 and width > 1 and height > 1


def _serialize_classified_action(item) -> dict[str, Any]:
    action = item.action
    states = list(action.states)

    data = item.to_dict()
    data["has_visible_bbox"] = _bbox_valid(action.bbox)
    data["is_showing"] = "showing" in states
    data["is_sensitive"] = "sensitive" in states
    data["is_enabled"] = "enabled" in states
    return data


def _filter_actions_by_kind(
    actions: list[dict[str, Any]],
    kind: ActionKind,
) -> list[dict[str, Any]]:
    return [action for action in actions if action.get("kind") == kind.value]


def _load_graph(*, app: str, maps_dir: Path, graph_path: Path | None) -> ExplorationGraph:
    if graph_path is not None:
        return ExplorationGraph.from_dict(
            json.loads(graph_path.read_text(encoding="utf-8")),
        )

    return GraphStore(maps_dir).load(app)


def build_active_root_scope_map(
    *,
    app: str,
    maps_dir: Path,
    graph_path: Path | None = None,
) -> dict[str, Any]:
    graph = _load_graph(app=app, maps_dir=maps_dir, graph_path=graph_path)

    states: dict[str, dict[str, Any]] = {}
    kind_counts: Counter[str] = Counter()
    total_active_root_actions = 0
    active_root_mismatch_count = 0
    missing_xml_count = 0

    for state_id, node in sorted(graph.nodes.items(), key=lambda item: item[0]):
        xml_path = _state_xml_path(node, maps_dir, graph.app_id)
        screenshot_path = _state_screenshot_path(node, maps_dir, graph.app_id)

        graph_active_root = dict(node.active_root)
        recomputed_active_root: dict[str, Any] | None = None
        active_root_actions: list[dict[str, Any]] = []

        if xml_path.exists():
            root = parse_a11y_xml(xml_path)
            active = resolve_active_root(root)
            recomputed_active_root = _active_root_payload(active)

            classified = classify_actions(extract_actions(active.node))
            active_root_actions = [_serialize_classified_action(item) for item in classified]

            for action in active_root_actions:
                kind_counts[str(action.get("kind", ""))] += 1

            total_active_root_actions += len(active_root_actions)
        else:
            missing_xml_count += 1

        active_root_matches_graph = False
        if recomputed_active_root is not None:
            active_root_matches_graph = _graph_active_root_matches(
                graph_active_root,
                recomputed_active_root,
            )
            if not active_root_matches_graph:
                active_root_mismatch_count += 1

        states[state_id] = {
            "state_id": state_id,
            "label": node.label,
            "depth": node.depth,
            "graph_active_root": graph_active_root,
            "recomputed_active_root": recomputed_active_root,
            "active_root_matches_graph": active_root_matches_graph,
            "artifacts": {
                "a11y_xml": str(xml_path),
                "screenshot": str(screenshot_path) if screenshot_path else None,
            },
            "active_root_actions": active_root_actions,
            "active_root_micro_actions": _filter_actions_by_kind(
                active_root_actions,
                ActionKind.MICRO,
            ),
            "active_root_input_actions": _filter_actions_by_kind(
                active_root_actions,
                ActionKind.INPUT,
            ),
            "active_root_ignored_actions": _filter_actions_by_kind(
                active_root_actions,
                ActionKind.IGNORED,
            ),
        }

    return {
        "schema_version": "1.0",
        "kind": "ui_explorer_active_root_scope_map",
        "app_id": graph.app_id,
        "root_state_id": graph.root_state_id,
        "usage_notes": {
            "active_root_actions": (
                "Actions extracted only from the recomputed active-root subtree "
                "of each saved A11Y snapshot."
            ),
            "active_root_micro_actions": (
                "Subset of active_root_actions classified as micro_candidate."
            ),
            "active_root_input_actions": (
                "Subset of active_root_actions classified as input_candidate."
            ),
            "active_root_ignored_actions": (
                "Subset of active_root_actions classified as ignored by the "
                "current exploration policy."
            ),
            "active_root_matches_graph": (
                "Whether recomputed active root matches the active_root summary "
                "stored in graph.json for the same state."
            ),
        },
        "summary": {
            "states": len(graph.nodes),
            "edges": len(graph.edges),
            "active_root_actions": total_active_root_actions,
            "active_root_micro_actions": kind_counts.get(ActionKind.MICRO.value, 0),
            "active_root_macro_actions": kind_counts.get(ActionKind.MACRO.value, 0),
            "active_root_input_actions": kind_counts.get(ActionKind.INPUT.value, 0),
            "active_root_ignored_actions": kind_counts.get(ActionKind.IGNORED.value, 0),
            "action_kind_counts": dict(sorted(kind_counts.items())),
            "active_root_mismatch_count": active_root_mismatch_count,
            "missing_xml_count": missing_xml_count,
            "completion": graph.completion,
        },
        "states": states,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build active-root-scoped action map from saved A11Y XML snapshots."
        ),
    )
    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument(
        "--graph",
        default=None,
        help="Optional graph.json path (defaults to data/maps/<app>/graph.json).",
    )
    parser.add_argument("--output", default=None)

    args = parser.parse_args()

    maps_dir = Path(args.maps)
    graph_path = Path(args.graph) if args.graph else None
    scope_map = build_active_root_scope_map(
        app=args.app,
        maps_dir=maps_dir,
        graph_path=graph_path,
    )

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = maps_dir / args.app / "agent_map_active_root_scope.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(scope_map, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = scope_map["summary"]
    print(json.dumps({
        "ok": True,
        "app_id": args.app,
        "graph": str(graph_path) if graph_path else str(maps_dir / args.app / "graph.json"),
        "output": str(output_path),
        "states": summary["states"],
        "active_root_actions": summary["active_root_actions"],
        "active_root_micro_actions": summary["active_root_micro_actions"],
        "active_root_macro_actions": summary["active_root_macro_actions"],
        "active_root_input_actions": summary["active_root_input_actions"],
        "active_root_ignored_actions": summary["active_root_ignored_actions"],
        "active_root_mismatch_count": summary["active_root_mismatch_count"],
        "missing_xml_count": summary["missing_xml_count"],
    }, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
