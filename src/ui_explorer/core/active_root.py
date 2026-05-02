from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ui_explorer.core.a11y_parser import A11YNode, walk


@dataclass(frozen=True)
class ActiveRoot:
    node: A11YNode
    reason: str
    kind: str  # main | dialog | alert | secondary_frame | menu | window_overlay


def _visible(nodes: Iterable[A11YNode]) -> list[A11YNode]:
    return [node for node in nodes if node.is_visible]


def _first_visible_frame(root: A11YNode) -> Optional[A11YNode]:
    for node in walk(root):
        if node.role == "frame" and node.is_visible:
            return node
    return None


def _visible_secondary_roots(root: A11YNode) -> list[A11YNode]:
    """
    Return visible dialog/alert/secondary frames.

    Secondary frame = visible frame whose name differs from the first visible main frame.
    This is intentionally simple for MVP.
    """
    nodes = list(walk(root))
    main_frame = _first_visible_frame(root)
    main_frame_name = main_frame.name if main_frame else None

    result: list[A11YNode] = []
    for node in nodes:
        if not node.is_visible:
            continue

        if node.role in {"dialog", "alert"}:
            result.append(node)
            continue

        if node.role == "frame" and main_frame_name is not None and node.name != main_frame_name:
            result.append(node)

    return result


def _visible_menu_roots(root: A11YNode) -> list[A11YNode]:
    """
    Return visible menu-like roots.

    We keep this conservative:
    - role == menu
    - role == window with menu/menu item descendants
    """
    result: list[A11YNode] = []

    for node in walk(root):
        if not node.is_visible:
            continue

        if node.role == "menu":
            result.append(node)
            continue

        if node.role == "window":
            descendants = list(walk(node))
            if any(d.role in {"menu", "menu item"} and d.is_visible for d in descendants):
                result.append(node)

    return result


def _visible_popover_roots(root: A11YNode) -> list[A11YNode]:
    """
    Return visible popover-like containers.

    Some GTK popovers are not exposed as role=menu/window. They appear as
    visible panels containing radio/menu/check items outside the main frame.
    """
    main_frame = _first_visible_frame(root)
    result: list[A11YNode] = []

    for node in walk(root):
        if not node.is_visible:
            continue
        if node is main_frame:
            continue

        descendants = list(walk(node))
        visible_controls = [
            d for d in descendants
            if d.is_visible and d.role in {"radio button", "menu item", "check box"}
        ]

        if len(visible_controls) >= 2:
            # Avoid selecting the whole main frame/panel by requiring a reasonably
            # small overlay-like box.
            if node.bbox.width <= 400 and node.bbox.height <= 400:
                result.append(node)

    return result


def resolve_active_root(root: A11YNode) -> ActiveRoot:
    """
    Resolve the active interaction root.

    Important:
    The last visible secondary/menu root is treated as topmost because many GTK apps
    append newer transient windows later in the A11Y tree.
    """
    secondary = _visible_secondary_roots(root)
    if secondary:
        node = secondary[-1]
        if node.role == "dialog":
            return ActiveRoot(node=node, kind="dialog", reason="visible dialog is topmost")
        if node.role == "alert":
            return ActiveRoot(node=node, kind="alert", reason="visible alert is topmost")
        return ActiveRoot(node=node, kind="secondary_frame", reason="visible secondary frame is topmost")

    menus = _visible_menu_roots(root)
    if menus:
        node = menus[-1]
        if node.role == "menu":
            return ActiveRoot(node=node, kind="menu", reason="visible menu is active overlay")
        return ActiveRoot(node=node, kind="window_overlay", reason="visible menu-like window is active overlay")

    popovers = _visible_popover_roots(root)
    if popovers:
        node = popovers[-1]
        return ActiveRoot(node=node, kind="window_overlay", reason="visible popover-like control group is active overlay")

    main_frame = _first_visible_frame(root)
    if main_frame is not None:
        return ActiveRoot(node=main_frame, kind="main", reason="no overlay found; using main frame")

    return ActiveRoot(node=root, kind="main", reason="no frame found; using application root")
