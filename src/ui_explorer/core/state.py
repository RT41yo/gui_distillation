from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ui_explorer.core.action_policy import ActionKind, classify_actions
from ui_explorer.core.actions import extract_actions
from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.a11y_parser import A11YNode, walk


@dataclass(frozen=True)
class StateSignature:
    state_id: str
    macro_hash: str
    content_hash: str
    active_root: dict
    macro_action_count: int
    visible_node_count: int
    macro_payload: dict
    content_payload: dict

    def to_dict(self, include_payload: bool = False) -> dict:
        data = {
            "state_id": self.state_id,
            "macro_hash": self.macro_hash,
            "content_hash": self.content_hash,
            "active_root": self.active_root,
            "macro_action_count": self.macro_action_count,
            "visible_node_count": self.visible_node_count,
            "signature_source": "a11y_only",
            "screenshot_used": False,
        }
        if include_payload:
            data["macro_payload"] = self.macro_payload
            data["content_payload"] = self.content_payload
        return data


def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _node_identity(node: A11YNode) -> dict:
    return {
        "role": node.role,
        "name": node.name,
        "description": node.description,
        "states": list(node.states),
        "bbox_visible": node.is_visible,
        "parent_path": list(node.parent_path),
        "depth": node.depth,
        "index": node.index,
    }


def _normalize_parent_path(parent_path: tuple[str, ...]) -> list[str]:
    """
    Normalize A11Y parent path for state identity.

    Keep semantic container path but avoid absolute/geometry-dependent data.
    """
    return list(parent_path)


def _action_identity_for_state(item) -> dict:
    action = item.action
    return {
        "role": action.role,
        "name": action.name,
        "description": action.description,
        "states": list(action.states),
        "parent_path": _normalize_parent_path(action.parent_path),
        "kind": item.kind.value,
        "priority": item.priority,
    }


def compute_state_signature(root: A11YNode) -> StateSignature:
    active = resolve_active_root(root)

    active_root_payload = {
        "kind": active.kind,
        "reason": active.reason,
        "role": active.node.role,
        "name": active.node.name,
        "description": active.node.description,
        "states": list(active.node.states),
        "bbox_visible": active.node.is_visible,
        "parent_path": list(active.node.parent_path),
    }

    active_visible_nodes = [
        node for node in walk(active.node)
        if node.is_visible
    ]

    # Macro actions are the exploration-relevant outgoing frontier.
    raw_actions = extract_actions(active.node)
    classified = classify_actions(raw_actions)
    macro_actions = [
        item for item in classified
        if item.kind == ActionKind.MACRO
    ]

    macro_payload = {
        "active_root": active_root_payload,
        "visible_interactive_macro_actions": [
            _action_identity_for_state(item)
            for item in macro_actions
        ],
        # Keep duplicate nodes: use list, not set.
        "visible_interactive_nodes": [],
    }

    # Content payload is allowed to be more sensitive to labels/text/value.
    # It is not the main node identity, but useful for classifying content_changed.
    content_payload = {
        "active_root": active_root_payload,
        "visible_nodes": [
            _node_identity(node)
            for node in active_visible_nodes
            if node.role in {
                "label",
                "text",
                "entry",
                "editbar",
                "push button",
                "toggle button",
                "radio button",
                "check box",
                "combo box",
                "menu item",
            }
        ],
    }

    macro_hash = _hash_payload(macro_payload)
    content_hash = _hash_payload(content_payload)

    return StateSignature(
        state_id=macro_hash[:12],
        macro_hash=macro_hash,
        content_hash=content_hash,
        active_root=active_root_payload,
        macro_action_count=len(macro_actions),
        visible_node_count=len(active_visible_nodes),
        macro_payload=macro_payload,
        content_payload=content_payload,
    )
