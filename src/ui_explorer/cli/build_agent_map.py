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

OVERLAY_LIKE_ACTIVE_ROOT_KINDS = frozenset({
    "dialog",
    "menu",
    "popover",
    "window_overlay",
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
    return list(parent_path)[-4:]


def _norm_identity_part(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _identity_key(role: Any, name: Any, description: Any) -> tuple[str, str, str]:
    return (
        _norm_identity_part(role),
        _norm_identity_part(name),
        _norm_identity_part(description),
    )


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

    # Agent-facing observed items should represent the currently visible UI,
    # not hidden GTK/A11Y model entries repeated across many states.
    if "showing" not in node.states:
        return None

    if not name and not description and node.role not in {"entry", "editbar"}:
        return None

    parent_path_tail = _compact_parent_path(node.parent_path)

    # No states/bbox in identity: same semantic item can move or change focus.
    payload = {
        "role": node.role,
        "name": name,
        "description": description,
        "parent_path_tail": parent_path_tail,
    }

    item: dict[str, Any] = {
        "item_id": _short_hash(payload),
        "role": node.role,
        "name": name,
        "description": description,
        "status": "observed_unverified",
        "states": _states_list(node.states),
        "parent_path_tail": parent_path_tail,
    }

    if _node_has_visible_bbox(node):
        item["visible_bbox_hint"] = node.bbox.as_list()

    return item


def _merge_observed_item(
    canonical_items: dict[str, dict[str, Any]],
    item: dict[str, Any],
) -> dict[str, Any]:
    item_id = item["item_id"]

    if item_id not in canonical_items:
        canonical_items[item_id] = dict(item)
        return canonical_items[item_id]

    existing = canonical_items[item_id]

    existing_states = set(existing.get("states", []))
    incoming_states = set(item.get("states", []))
    existing["states"] = sorted(existing_states | incoming_states)

    if "visible_bbox_hint" not in existing and "visible_bbox_hint" in item:
        existing["visible_bbox_hint"] = item["visible_bbox_hint"]

    if not existing.get("description") and item.get("description"):
        existing["description"] = item["description"]

    return existing


def _observed_item_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": item["item_id"],
        "role": item.get("role", ""),
        "name": item.get("name", ""),
        "description": item.get("description", ""),
    }


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


def _incoming_action_from_edge(
    edge: GraphEdge,
    *,
    from_depth: int | None,
) -> dict[str, Any]:
    action = edge.action
    bbox = _action_bbox_or_none(action)

    item: dict[str, Any] = {
        "from_state": edge.from_state,
        "from_depth": from_depth,
        "edge_id": edge.edge_id,
        "action_key": edge.action_key,
        "role": action.get("role", ""),
        "name": action.get("name", ""),
        "description": action.get("description", ""),
        "edge_status": edge.status.value,
        "method": "bbox_click" if bbox is not None else "verified_without_agent_bbox",
        "created_order": edge.created_order,
    }

    if bbox is not None:
        item["bbox"] = bbox

    return item


def _choose_primary_incoming_action(
    *,
    state_id: str,
    incoming_actions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = [
        item
        for item in incoming_actions
        if item.get("from_state") and item.get("from_state") != state_id
    ]

    if not candidates:
        return None

    candidates.sort(key=lambda item: (
        item.get("from_depth") is None,
        item.get("from_depth") if item.get("from_depth") is not None else 10**9,
        item.get("created_order") if item.get("created_order") is not None else 10**9,
        str(item.get("from_state", "")),
        str(item.get("edge_id", "")),
    ))

    return dict(candidates[0])


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
        result[edge.from_state].add(_identity_key(
            action.get("role", ""),
            action.get("name", ""),
            action.get("description", ""),
        ))

    return result


def _item_index_key(name: str, role: str) -> str:
    return _short_hash({
        "name": name.casefold(),
        "role": role,
    })


def _build_item_index(
    states: dict[str, dict[str, Any]],
    items: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    index: dict[str, Any] = {}

    for state_id, state in states.items():
        for item in state.get("verified_actions", []):
            name = (item.get("name") or "").strip()
            role = (item.get("role") or "").strip()

            if not name:
                continue

            key = _item_index_key(name, role)

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
            entry["verified_action_count"] += 1

            if state_id not in entry["states"]:
                entry["states"].append(state_id)

            status = item.get("status")
            if status and status not in entry["statuses"]:
                entry["statuses"].append(status)

        for ref_item in state.get("observed_items", []):
            ref = ref_item.get("ref")
            if not ref:
                continue

            full_item = items.get(ref, ref_item)
            name = (full_item.get("name") or ref_item.get("name") or "").strip()
            role = (full_item.get("role") or ref_item.get("role") or "").strip()

            if not name:
                continue

            key = _item_index_key(name, role)

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
            entry["observed_item_count"] += 1

            if state_id not in entry["states"]:
                entry["states"].append(state_id)

            status = full_item.get("status") or ref_item.get("status")
            if status and status not in entry["statuses"]:
                entry["statuses"].append(status)

    return dict(sorted(
        index.items(),
        key=lambda kv: (
            kv[1]["name"].casefold(),
            kv[1]["role"],
        ),
    ))


def _build_verified_action_index(states: dict[str, dict[str, Any]]) -> dict[str, Any]:
    index: dict[str, Any] = {}

    for state_id, state in states.items():
        for action in state.get("verified_actions", []):
            name = (action.get("name") or "").strip()
            role = (action.get("role") or "").strip()

            if not name:
                continue

            key = _item_index_key(name, role)

            entry = index.setdefault(key, {
                "name": name,
                "role": role,
                "occurrences": 0,
                "states": [],
                "actions": [],
            })

            entry["occurrences"] += 1

            if state_id not in entry["states"]:
                entry["states"].append(state_id)

            entry["actions"].append({
                "state_id": state_id,
                "state_depth": state.get("depth"),
                "edge_id": action.get("edge_id"),
                "edge_status": action.get("edge_status"),
                "to_state": action.get("to_state"),
                "description": action.get("description", ""),
                "has_bbox": "bbox" in action,
            })

    return dict(sorted(
        index.items(),
        key=lambda kv: (
            kv[1]["name"].casefold(),
            kv[1]["role"],
        ),
    ))


def _known_identities_for_state(
    state: dict[str, Any],
    items: dict[str, dict[str, Any]],
) -> set[tuple[str, str, str]]:
    identities: set[tuple[str, str, str]] = set()

    for action in state.get("verified_actions", []):
        identities.add(_identity_key(
            action.get("role", ""),
            action.get("name", ""),
            action.get("description", ""),
        ))

    for ref_item in state.get("observed_items", []):
        identities.add(_identity_for_observed_ref(ref_item, items))

    return identities


def _identity_for_observed_ref(
    ref_item: dict[str, Any],
    items: dict[str, dict[str, Any]],
) -> tuple[str, str, str]:
    ref = ref_item.get("ref")
    full_item = items.get(ref, ref_item)

    return _identity_key(
        full_item.get("role", ref_item.get("role", "")),
        full_item.get("name", ref_item.get("name", "")),
        full_item.get("description", ref_item.get("description", "")),
    )


def _choose_delta_base_state(
    *,
    state_id: str,
    root_state_id: str | None,
    state: dict[str, Any],
    states: dict[str, dict[str, Any]],
) -> str | None:
    if state_id == root_state_id:
        return None

    primary = state.get("primary_incoming_action")
    if primary:
        from_state = primary.get("from_state")
        if from_state in states and from_state != state_id:
            return from_state

    incoming = [
        item
        for item in state.get("incoming_actions", [])
        if item.get("from_state") in states and item.get("from_state") != state_id
    ]

    if incoming:
        incoming.sort(key=lambda item: (
            item.get("from_depth") is None,
            item.get("from_depth") if item.get("from_depth") is not None else 10**9,
            item.get("created_order") if item.get("created_order") is not None else 10**9,
            str(item.get("from_state", "")),
            str(item.get("edge_id", "")),
        ))
        return incoming[0]["from_state"]

    if root_state_id and root_state_id in states and root_state_id != state_id:
        return root_state_id

    return None


def _add_delta_observed_items(
    *,
    states: dict[str, dict[str, Any]],
    items: dict[str, dict[str, Any]],
    root_state_id: str | None,
) -> None:
    for state_id, state in states.items():
        base_state_id = _choose_delta_base_state(
            state_id=state_id,
            root_state_id=root_state_id,
            state=state,
            states=states,
        )

        state["delta_base_state"] = base_state_id

        if base_state_id is None:
            state["delta_observed_items"] = []
            continue

        base_state = states[base_state_id]
        base_identities = _known_identities_for_state(base_state, items)

        delta: list[dict[str, Any]] = []
        seen_delta_refs: set[str] = set()

        for ref_item in state.get("observed_items", []):
            ref = ref_item.get("ref")
            if not ref or ref in seen_delta_refs:
                continue

            if _identity_for_observed_ref(ref_item, items) in base_identities:
                continue

            delta.append(ref_item)
            seen_delta_refs.add(ref)

        state["delta_observed_items"] = delta


def _active_root_kind(state: dict[str, Any]) -> str:
    active_root = state.get("active_root") or {}
    return str(active_root.get("kind") or "").strip().casefold()


def _add_scoped_observed_items(states: dict[str, dict[str, Any]]) -> None:
    """Add best-effort scoped observed items without changing exploration.

    We do not have a stable active-root selector in graph.json yet, so this is
    deliberately conservative:
    - main states use the complete observed context with high confidence;
    - overlay/menu-like states use delta items when available with medium
      confidence, because the full A11Y dump often includes background UI;
    - otherwise we fall back to observed_items and mark confidence as low.
    """
    for state in states.values():
        kind = _active_root_kind(state)
        observed = list(state.get("observed_items", []))
        delta = list(state.get("delta_observed_items", []))

        if kind == "main":
            scoped = observed
            source = "observed_items_main_root"
            confidence = "high"
        elif kind in OVERLAY_LIKE_ACTIVE_ROOT_KINDS and delta:
            scoped = delta
            source = "delta_observed_items_overlay_hint"
            confidence = "medium"
        elif delta:
            scoped = delta
            source = "delta_observed_items_hint"
            confidence = "medium"
        elif observed:
            scoped = observed
            source = "fallback_observed_items"
            confidence = "low"
        else:
            scoped = []
            source = "unresolved"
            confidence = "low"

        state["scoped_observed_items"] = scoped
        state["scoped_observed_source"] = source
        state["scoped_observed_confidence"] = confidence


def _capability_from_verified_action(action: dict[str, Any]) -> dict[str, Any]:
    result = {
        "kind": "verified_action",
        "edge_id": action.get("edge_id"),
        "role": action.get("role", ""),
        "name": action.get("name", ""),
        "description": action.get("description", ""),
        "status": action.get("status", "verified"),
        "method": action.get("method"),
        "edge_status": action.get("edge_status"),
        "to_state": action.get("to_state"),
        "has_bbox": "bbox" in action,
    }

    if "bbox" in action:
        result["bbox"] = action["bbox"]

    return result


def _capability_from_observed_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "observed_item",
        "ref": item.get("ref"),
        "role": item.get("role", ""),
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "status": "observed_unverified",
    }


def _add_state_capabilities(states: dict[str, dict[str, Any]]) -> None:
    for state in states.values():
        capabilities: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()

        for action in state.get("verified_actions", []):
            key = (
                "verified_action",
                str(action.get("role", "")),
                str(action.get("name", "")),
                str(action.get("description", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            capabilities.append(_capability_from_verified_action(action))

        scoped_confidence = state.get("scoped_observed_confidence")
        scoped_source = state.get("scoped_observed_source")

        if scoped_confidence == "low":
            observed_source = state.get("delta_observed_items", [])
            capability_source = (
                "verified_actions_plus_delta_observed_items_low_confidence_scoped"
            )
        else:
            observed_source = state.get("scoped_observed_items", [])
            capability_source = "verified_actions_plus_scoped_observed_items"

        for item in observed_source:
            key = (
                "observed_item",
                str(item.get("role", "")),
                str(item.get("name", "")),
                str(item.get("description", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            capabilities.append(_capability_from_observed_ref(item))

        state["state_capabilities"] = capabilities
        state["state_capabilities_source"] = capability_source
        state["state_capabilities_scoped_source"] = scoped_source
        state["state_capabilities_scoped_confidence"] = scoped_confidence


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

    incoming_edges_by_state: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in verified_edges:
        if edge.to_state:
            incoming_edges_by_state[edge.to_state].append(edge)

    states: dict[str, dict[str, Any]] = {}
    canonical_items: dict[str, dict[str, Any]] = {}

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

        incoming_actions = [
            _incoming_action_from_edge(
                edge,
                from_depth=graph.nodes[edge.from_state].depth
                if edge.from_state in graph.nodes
                else None,
            )
            for edge in sorted(
                incoming_edges_by_state.get(state_id, []),
                key=lambda edge: (
                    graph.nodes[edge.from_state].depth
                    if edge.from_state in graph.nodes
                    else 10**9,
                    edge.created_order,
                    edge.edge_id,
                ),
            )
        ]

        if state_id == graph.root_state_id:
            primary_incoming_action = None
        else:
            primary_incoming_action = _choose_primary_incoming_action(
                state_id=state_id,
                incoming_actions=incoming_actions,
            )

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

                identity = _identity_key(
                    item["role"],
                    item["name"],
                    item["description"],
                )

                # Avoid duplicating normal verified actions in observed_items.
                # They already appear in verified_actions with transitions.
                if identity in verified_identity:
                    continue

                canonical_item = _merge_observed_item(canonical_items, item)
                item_id = canonical_item["item_id"]

                if item_id in seen_observed_ids:
                    continue

                seen_observed_ids.add(item_id)
                observed_items.append(_observed_item_ref(canonical_item))

        states[state_id] = {
            "state_id": state_id,
            "label": node.label,
            "depth": node.depth,
            "active_root": {
                "kind": node.active_root.get("kind"),
                "role": node.active_root.get("role"),
                "name": node.active_root.get("name"),
            },
            "primary_incoming_action": primary_incoming_action,
            "incoming_actions": incoming_actions,
            "verified_actions": state_verified_actions,
            "observed_items": observed_items,
        }

    _add_delta_observed_items(
        states=states,
        items=canonical_items,
        root_state_id=graph.root_state_id,
    )
    _add_scoped_observed_items(states)
    _add_state_capabilities(states)

    observed_item_refs_count = sum(
        len(state.get("observed_items", []))
        for state in states.values()
    )
    delta_observed_item_refs_count = sum(
        len(state.get("delta_observed_items", []))
        for state in states.values()
    )
    scoped_observed_item_refs_count = sum(
        len(state.get("scoped_observed_items", []))
        for state in states.values()
    )
    state_capabilities_count = sum(
        len(state.get("state_capabilities", []))
        for state in states.values()
    )

    result = {
        "schema_version": "1.2",
        "kind": "ui_explorer_agent_map",
        "app_id": graph.app_id,
        "root_state_id": graph.root_state_id,
        "usage_notes": {
            "verified_actions": (
                "Actions confirmed by exploration. Use these for graph-based "
                "navigation and verified transitions."
            ),
            "incoming_actions": (
                "Verified actions from other states that lead into this state. "
                "Use these to understand how a state was opened or reached."
            ),
            "primary_incoming_action": (
                "Preferred incoming action for understanding the main way this "
                "state is reached. Chosen generically by shallowest non-self "
                "incoming source, then created_order. Root state has no primary "
                "incoming action."
            ),
            "items": (
                "Canonical observed item definitions keyed by item_id. These "
                "items are observed as showing in saved A11Y state snapshots. "
                "They are not confirmed execution paths."
            ),
            "states.observed_items": (
                "Per-state short references to top-level items. This is the "
                "complete visible observed context for the state."
            ),
            "states.delta_observed_items": (
                "Diagnostic hint: observed item refs that are new relative to "
                "the state's nearest incoming source state. This is not a "
                "complete description of the state."
            ),
            "states.scoped_observed_items": (
                "Best-effort important/scoped observed refs. Without an exact "
                "active-root selector in graph.json, overlay/menu states use "
                "delta hints when available and are marked with confidence."
            ),
            "states.state_capabilities": (
                "Agent-facing list combining verified actions and scoped "
                "observed items. If scoped_observed_confidence is low, observed "
                "fallback items are not included; only delta hints are added."
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
            "items": len(canonical_items),
            "observed_item_refs": observed_item_refs_count,
            "delta_observed_item_refs": delta_observed_item_refs_count,
            "scoped_observed_item_refs": scoped_observed_item_refs_count,
            "state_capabilities": state_capabilities_count,
        },
        "items": dict(sorted(
            canonical_items.items(),
            key=lambda kv: (
                str(kv[1].get("role", "")),
                str(kv[1].get("name", "")).casefold(),
                str(kv[1].get("description", "")).casefold(),
                kv[0],
            ),
        )),
        "states": states,
    }

    result["item_index"] = _build_item_index(states, result["items"])
    result["verified_action_index"] = _build_verified_action_index(states)

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
        "items": agent_map["summary"]["items"],
        "observed_item_refs": agent_map["summary"]["observed_item_refs"],
        "delta_observed_item_refs": agent_map["summary"]["delta_observed_item_refs"],
        "scoped_observed_item_refs": agent_map["summary"]["scoped_observed_item_refs"],
        "state_capabilities": agent_map["summary"]["state_capabilities"],
        "item_index": len(agent_map["item_index"]),
        "verified_action_index": len(agent_map["verified_action_index"]),
    }, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
