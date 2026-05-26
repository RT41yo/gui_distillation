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
    "menu",
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


def _parent_path_text(node: A11YNode) -> str:
    return " / ".join(node.parent_path).lower()


def _is_top_menu_bar_action(node: A11YNode) -> bool:
    return (
        node.role == "menu"
        and bool((node.name or "").strip())
        and bool(node.parent_path)
        and node.parent_path[-1].lower() == "menu bar"
    )


def make_semantic_action_key(node: A11YNode) -> tuple:
    """
    Semantic de-duplication key.

    LibreOffice can expose the same top-level menu bar twice through different
    A11Y subtrees, for example:
      - scroll pane / viewport / menu bar
      - root pane / menu bar

    The regular action_key intentionally preserves parent_path/bbox for stable
    execution. But for extraction we do not want duplicate frontier actions:
    File/Edit/.../Help should appear once.
    """
    if _is_top_menu_bar_action(node):
        return ("top_menu_bar", node.name.strip().lower())

    return (
        "raw",
        node.role,
        node.name.strip().lower(),
        node.description.strip().lower(),
        tuple(node.bbox.as_list()),
        tuple(node.parent_path),
    )


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
    seen_action_keys: set[str] = set()
    seen_semantic_keys: set[tuple] = set()

    for node in walk(active_root):
        # If the active root is an opened menu, do not create an action
        # for the menu root itself. Example: opened File menu should expose
        # New/Open/Save..., but not File -> File.
        if node is active_root and active_root.role == "menu":
            continue

        if not is_actionable(node):
            continue

        semantic_key = make_semantic_action_key(node)
        if semantic_key in seen_semantic_keys:
            continue
        seen_semantic_keys.add(semantic_key)

        key = make_action_key(node)
        if key in seen_action_keys:
            continue
        seen_action_keys.add(key)

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
