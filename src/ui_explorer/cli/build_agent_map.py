from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ui_explorer.core.a11y_parser import A11YNode, parse_a11y_xml, walk
from ui_explorer.graph.models import EdgeStatus, GraphEdge, StateNode
from ui_explorer.graph.store import GraphStore


OBSERVED_ROLES = frozenset({
    "push button",
    "toggle button",
    "radio button",
    "check box",
    "combo box",
    "menu",
    "menu item",
    "tab",
    "tree item",
    "link",
    "spin button",
    "entry",
    "editbar",
    "table cell",
    "list item",
    "list box",
    "row",
})

EXECUTION_VERIFIED_STATUSES = frozenset({
    EdgeStatus.CONFIRMED,
    EdgeStatus.SAME_STATE,
    EdgeStatus.CONTENT_CHANGED,
    EdgeStatus.FOCUS_CHANGED,
    EdgeStatus.SELECTION_CHANGED,
})


def _bbox_valid(bbox: list[int] | tuple[int, int, int, int]) -> bool:
    x, y, width, height = bbox
    return x >= 0 and y >= 0 and width > 1 and height > 1


def _states_list(states: tuple[str, ...] | list[str]) -> list[str]:
    return sorted(str(s) for s in states)


def _short_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _compact_parent_path(parent_path: tuple[str, ...] | list[str]) -> list[str]:
    # Full parent_path is useful for debugging, but too noisy for an
    # agent-facing map.
    return list(parent_path)[-4:]


def _node_has_visible_bbox(node: A11YNode) -> bool:
    bbox = node.bbox.as_list()
    return _bbox_valid(bbox) and "showing" in node.states


def _action_bbox_or_none(action: dict[str, Any]) -> list[int] | None:
    bbox = action.get("bbox")

    if not isinstance(bbox, list):
        return None

    if len(bbox) != 4:
        return None

    if not _bbox_valid(bbox):
        return None

    states = action.get("states") or []
    if "showing" not in states:
        return None

    return bbox


def _observed_item_from_node(node: A11YNode) -> dict[str, Any] | None:
    name = node.name.strip()
    description = node.description.strip()

    if node.role not in OBSERVED_ROLES:
        return None

    # Skip anonymous containers/items in the first compact agent-facing version.
    if not name and not description and node.role not in {"entry", "editbar"}:
        return None

    payload = {
        "role": node.role,
        "name": name,
        "description": description,
        "parent_path_tail": _compact_parent_path(node.parent_path),
    }

    item: dict[str, Any] = {
        "item_id": _short_hash(payload),
        "role": node.role,
        "name": name,
        "description": description,
        "status": "observed_unverified",
        "states": _states_list(node.states),
        "parent_path_tail": _compact_parent_path(node.parent_path),
    }

    # Do not expose invalid bbox/null bbox for observed-only items.
    # If the element has a valid visible bbox but was not verified by graph
    # exploration, preserve that as a hint, not as a confirmed execution path.
    if _node_has_visible_bbox(node):
        item["visible_bbox_hint"] = node.bbox.as_list()

    return item


def _verified_action_from_edge(edge: GraphEdge, from_depth: int) -> dict[str, Any]:
    action = edge.action
    bbox = _action_bbox_or_none(action)

    item: dict[str, Any] = {
        "edge_id": edge.edge_id,
        "action_key": edge.action_key,
        "role": action.get("role", ""),
        "name": action.get("name", ""),
        "description": action.get("description", ""),
        "status": "verified",
        "method": "bbox_click" if bbox is not None else "verified_without_agent_bbox",
        "from_depth": from_depth,
        "edge_status": edge.status.value,
        "to_state": edge.to_state,
    }

    if bbox is not None:
        item["bbox"] = bbox

    return item


def _state_xml_path(node: StateNode, maps_dir: Path, app_id: str) -> Path:
    xml_path = Path(node.xml_path)

    if xml_path.exists():
        return xml_path

    return maps_dir / app_id / "states" / node.state_id / "a11y.xml"


def _verified_action_keys_by_state(
    edges: list[GraphEdge],
) -> dict[str, set[tuple[str, str, str]]]:
    result: dict[str, set[tuple[str, str, str]]] = defaultdict(set)

    for edge in edges:
        if edge.status not in EXECUTION_VERIFIED_STATUSES:
            continue

        action = edge.action
        result[edge.from_state].add((
            str(action.get("role", "")),
            str(action.get("name", "")),
            str(action.get("description", "")),
        ))

    return result


def _build_item_index(states: dict[str, dict[str, Any]]) -> dict[str, Any]:
    index: dict[str, Any] = {}

    for state_id, state in states.items():
        for section in ("verified_actions", "observed_items"):
            for item in state.get(section, []):
                name = (item.get("name") or "").strip()
                role = (item.get("role") or "").strip()

                if not name:
                    continue

                key_payload = {
                    "name": name.casefold(),
                    "role": role,
                }
                key = _short_hash(key_payload)

                entry = index.setdefault(key, {
                    "name": name,
                    "role": role,
                    "states": [],
                    "occurrences": 0,
                    "verified_action_count": 0,
                    "observed_item_count": 0,
                    "statuses": [],
                })

                entry["occurrences"] += 1

                if state_id not in entry["states"]:
                    entry["states"].append(state_id)

                status = item.get("status")
                if status and status not in entry["statuses"]:
                    entry["statuses"].append(status)

                if section == "verified_actions":
                    entry["verified_action_count"] += 1
                else:
                    entry["observed_item_count"] += 1

    return dict(sorted(
        index.items(),
        key=lambda kv: (
            kv[1]["name"].casefold(),
            kv[1]["role"],
        ),
    ))


def build_agent_map(app: str, maps_dir: Path) -> dict[str, Any]:
    store = GraphStore(maps_dir)
    graph = store.load(app)

    edge_status_counts = Counter(edge.status.value for edge in graph.edges.values())
    node_depth_counts = Counter(node.depth for node in graph.nodes.values())

    verified_edges = [
        edge
        for edge in graph.edges.values()
        if edge.status in EXECUTION_VERIFIED_STATUSES
    ]

    verified_keys = _verified_action_keys_by_state(verified_edges)

    states: dict[str, dict[str, Any]] = {}

    sorted_edges = sorted(
        graph.edges.values(),
        key=lambda edge: (edge.created_order, edge.edge_id),
    )

    for state_id, node in sorted(
        graph.nodes.items(),
        key=lambda item: (item[1].depth, item[0]),
    ):
        state_verified_actions = [
            _verified_action_from_edge(edge, from_depth=node.depth)
            for edge in sorted_edges
            if edge.from_state == state_id
            and edge.status in EXECUTION_VERIFIED_STATUSES
        ]

        observed_items: list[dict[str, Any]] = []

        xml_path = _state_xml_path(node, maps_dir, graph.app_id)
        if xml_path.exists():
            root = parse_a11y_xml(xml_path)

            seen_observed_ids: set[str] = set()
            verified_identity = verified_keys.get(state_id, set())

            for a11y_node in walk(root):
                item = _observed_item_from_node(a11y_node)
                if item is None:
                    continue

                identity = (
                    item["role"],
                    item["name"],
                    item["description"],
                )

                # Avoid duplicating normal verified actions in observed_items.
                # They already appear in verified_actions with transitions.
                if identity in verified_identity:
                    continue

                if item["item_id"] in seen_observed_ids:
                    continue

                seen_observed_ids.add(item["item_id"])
                observed_items.append(item)

        states[state_id] = {
            "state_id": state_id,
            "label": node.label,
            "depth": node.depth,
            "active_root": {
                "kind": node.active_root.get("kind"),
                "role": node.active_root.get("role"),
                "name": node.active_root.get("name"),
            },
            "verified_actions": state_verified_actions,
            "observed_items": observed_items,
        }

    result = {
        "schema_version": "1.0",
        "kind": "ui_explorer_agent_map",
        "app_id": graph.app_id,
        "root_state_id": graph.root_state_id,
        "usage_notes": {
            "verified_actions": (
                "Actions confirmed by exploration. Use these for graph-based "
                "navigation and verified transitions."
            ),
            "observed_items": (
                "Semantic UI items observed in A11Y snapshots. They may "
                "represent capabilities, menu options, latent UI model entries, "
                "or unverified controls. They are not confirmed execution paths."
            ),
        },
        "summary": {
            "states": len(graph.nodes),
            "edges": len(graph.edges),
            "edge_status_counts": dict(sorted(edge_status_counts.items())),
            "node_depth_counts": {
                str(k): v
                for k, v in sorted(node_depth_counts.items())
            },
            "max_depth": max(
                (node.depth for node in graph.nodes.values()),
                default=0,
            ),
            "pending_edges": graph.completion.get("pending_edges", 0),
            "completion": graph.completion,
        },
        "states": states,
    }

    result["item_index"] = _build_item_index(states)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build compact agent-facing UI map from exploration graph."
    )
    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--output", default=None)

    args = parser.parse_args()

    maps_dir = Path(args.maps)
    agent_map = build_agent_map(app=args.app, maps_dir=maps_dir)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = maps_dir / args.app / "agent_map.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(agent_map, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps({
        "ok": True,
        "app_id": args.app,
        "output": str(output_path),
        "states": agent_map["summary"]["states"],
        "edges": agent_map["summary"]["edges"],
        "item_index": len(agent_map["item_index"]),
    }, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
