from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from ui_explorer.core.a11y_parser import A11YNode, walk


ACTIONABLE_ROLES = frozenset({
    "push button",
    "toggle button",
    "radio button",
    "check box",
    "combo box",
    "menu item",
    "tab",
    "tree item",
    "link",
    "spin button",
    "entry",
    "editbar",
})


@dataclass(frozen=True)
class UIAction:
    action_key: str
    role: str
    name: str
    description: str
    states: tuple[str, ...]
    bbox: tuple[int, int, int, int]
    parent_path: tuple[str, ...]
    depth: int

    def to_dict(self) -> dict:
        return {
            "action_key": self.action_key,
            "role": self.role,
            "name": self.name,
            "description": self.description,
            "states": list(self.states),
            "bbox": list(self.bbox),
            "parent_path": list(self.parent_path),
            "depth": self.depth,
        }


def make_action_key(node: A11YNode) -> str:
    payload = {
        "role": node.role,
        "name": node.name,
        "description": node.description,
        "states": list(node.states),
        "bbox": node.bbox.as_list(),
        "parent_path": list(node.parent_path),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def is_actionable(node: A11YNode) -> bool:
    if not node.is_visible:
        return False
    if node.role not in ACTIONABLE_ROLES:
        return False
    # Безымянные кнопки/элементы пока не берём: их нельзя стабильно логировать.
    # Позже можно добавить fallback через role + bbox + parent_path.
    if not node.name and node.role not in {"entry", "editbar"}:
        return False
    return True


def extract_actions(active_root: A11YNode) -> list[UIAction]:
    actions: list[UIAction] = []
    seen: set[str] = set()

    for node in walk(active_root):
        if not is_actionable(node):
            continue

        key = make_action_key(node)
        if key in seen:
            continue
        seen.add(key)

        actions.append(
            UIAction(
                action_key=key,
                role=node.role,
                name=node.name,
                description=node.description,
                states=node.states,
                bbox=tuple(node.bbox.as_list()),
                parent_path=node.parent_path,
                depth=node.depth,
            )
        )

    return actions


def summarize_actions(actions: Iterable[UIAction]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action.role] = counts.get(action.role, 0) + 1
    return dict(sorted(counts.items()))
