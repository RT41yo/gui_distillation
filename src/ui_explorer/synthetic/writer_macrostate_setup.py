from __future__ import annotations

from typing import Any

from ui_explorer.synthetic.scope_index import ScopeIndex
from ui_explorer.synthetic.writer_fixtures import vm_window_name

WRITER_ROOT_FRAME_SELECTOR = {
    "role": "frame",
    "name_contains": "LibreOffice Writer",
    "require_bbox": False,
}


def find_navigation_path(
    agent_states: dict[str, Any],
    *,
    root_state_id: str,
    target_state_id: str,
) -> list[dict[str, Any]]:
    if target_state_id == root_state_id:
        return []

    edges: list[dict[str, Any]] = []
    current = target_state_id
    seen: set[str] = set()

    while current != root_state_id:
        if current in seen:
            raise ValueError(f"cycle while resolving navigation path for {target_state_id}")
        seen.add(current)

        state = agent_states.get(current)
        if not isinstance(state, dict):
            raise KeyError(f"unknown macro state id: {current}")

        incoming = state.get("primary_incoming_action")
        if not isinstance(incoming, dict):
            raise ValueError(f"no primary incoming action for state {current}")

        bbox = incoming.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise ValueError(f"missing bbox on incoming action for state {current}")

        edges.append(incoming)
        from_state = incoming.get("from_state")
        if not isinstance(from_state, str) or not from_state:
            raise ValueError(f"missing from_state on incoming action for state {current}")
        current = from_state

    edges.reverse()
    return edges


def build_active_root_selector(scope_state: dict[str, Any]) -> dict[str, Any]:
    active = scope_state.get("recomputed_active_root") or scope_state.get("graph_active_root") or {}
    kind = str(active.get("kind") or "").strip().lower()
    role = str(active.get("role") or "").strip()
    name = str(active.get("name") or "").strip()

    if kind in {"", "main"} or (role == "frame" and not name):
        return dict(WRITER_ROOT_FRAME_SELECTOR)

    selector: dict[str, Any] = {"require_bbox": False}
    if role:
        selector["role"] = role
    if name:
        selector["name"] = name
    elif kind:
        selector["name_contains"] = kind
    if kind in {"menu", "dialog"} or role.lower().replace(" ", "-") in {"menu", "dialog"}:
        selector["require_bbox"] = True
        selector["states"] = {"showing": True, "visible": True}
    return selector


def build_navigation_steps(navigation_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index, edge in enumerate(navigation_edges):
        role = edge.get("role")
        name = edge.get("name")
        op = "click" if index == 0 else "move"
        selector: dict[str, Any] = {
            "require_bbox": True,
            "states": {"showing": True, "visible": True},
        }
        if role:
            selector["role"] = role
        if name:
            selector["name"] = name
        steps.append({
            "op": op,
            "selector": selector,
            "meta": {
                "edge_id": edge.get("edge_id"),
                "role": role,
                "name": name,
                "recorded_bbox": edge.get("bbox"),
            },
        })
        steps.append({"op": "sleep", "seconds": 0.8})
    return steps


def build_writer_macrostate_preflight(
    scope_index: ScopeIndex,
    *,
    macro_state_id: str,
    vm_document_path: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    root_state_id = scope_index.agent_map.get("root_state_id")
    if not isinstance(root_state_id, str) or not root_state_id:
        return None, {
            "status": "unsupported",
            "reason": "agent_map missing root_state_id",
            "macro_state_id": macro_state_id,
        }

    if macro_state_id not in scope_index.agent_states:
        return None, {
            "status": "unsupported",
            "reason": "unknown macro_state_id",
            "macro_state_id": macro_state_id,
        }

    scope_state = scope_index.get_scope_state(macro_state_id)
    if scope_state.get("active_root_matches_graph") is False:
        return None, {
            "status": "active_root_mismatch",
            "reason": "scope map active_root does not match graph summary",
            "macro_state_id": macro_state_id,
        }

    try:
        navigation_edges = find_navigation_path(
            scope_index.agent_states,
            root_state_id=root_state_id,
            target_state_id=macro_state_id,
        )
    except (KeyError, ValueError) as exc:
        return None, {
            "status": "unsupported",
            "reason": str(exc),
            "macro_state_id": macro_state_id,
        }

    active_root = scope_state.get("recomputed_active_root") or scope_state.get("graph_active_root") or {}
    steps: list[dict[str, Any]] = [
        {
            "op": "wait_for",
            "selector": dict(WRITER_ROOT_FRAME_SELECTOR),
        },
    ]
    steps.extend(build_navigation_steps(navigation_edges))
    steps.append({
        "op": "assert",
        "selector": build_active_root_selector(scope_state),
    })

    window_name = vm_window_name(vm_document_path)
    setup_block = {
        "type": "a11y_preflight",
        "parameters": {
            "steps": steps,
            "timeout_seconds": 30,
            "screenshot_on_failure": True,
        },
    }
    provenance = {
        "status": "ready",
        "macro_state_id": macro_state_id,
        "root_state_id": root_state_id,
        "navigation_edge_count": len(navigation_edges),
        "navigation_edges": [
            {
                "edge_id": edge.get("edge_id"),
                "from_state": edge.get("from_state"),
                "role": edge.get("role"),
                "name": edge.get("name"),
                "bbox": edge.get("bbox"),
            }
            for edge in navigation_edges
        ],
        "active_root": {
            "kind": active_root.get("kind"),
            "role": active_root.get("role"),
            "name": active_root.get("name"),
        },
        "window_name": window_name,
        "preflight_step_count": len(steps),
    }
    return setup_block, provenance
