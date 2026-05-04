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
    Detect compact foreground-like popovers that are not exposed as role=menu/dialog.

    Important: do NOT classify ordinary calculator button grids as overlays.

    A compact container is considered an overlay only if it has strong overlay evidence:
    - radio/menu/list/check controls;
    - option-list names like bit/place;
    - store/memory names like variable/rand/store-value description;
    - input controls inside a compact container.

    This catches GTK popovers such as:
    - Word Size selector: 64-bit / 32-bit / 16-bit / 8-bit
    - Shift selector: 1 place / ... / 15 places
    - Store popover: rand + variable/store button
    """
    main_frame = _first_visible_frame(root)

    container_roles = {
        "window",
        "panel",
        "filler",
        "viewport",
        "scroll pane",
        "list",
        "list box",
        "combo box",
    }

    strong_control_roles = {
        "radio button",
        "check box",
        "menu item",
        "list item",
        "table cell",
        "row",
    }

    input_roles = {
        "entry",
        "editbar",
        "text entry",
        "password text",
        "spin button",
    }

    content_roles = {
        "push button",
        "toggle button",
        "button",
        "radio button",
        "check box",
        "menu item",
        "list item",
        "entry",
        "editbar",
        "text entry",
        "spin button",
        "label",
        "text",
        "static",
    }

    main_area = None
    if main_frame and main_frame.bbox:
        main_area = main_frame.bbox.width * main_frame.bbox.height

    candidates: list[tuple[int, A11YNode]] = []

    for node in walk(root):
        if not node.is_visible:
            continue
        if node is main_frame:
            continue
        if node.role not in container_roles:
            continue
        if not node.bbox or node.bbox.width <= 1 or node.bbox.height <= 1:
            continue

        width = node.bbox.width
        height = node.bbox.height
        area = width * height

        # Exclude full-window / large layout containers.
        if main_area and area > main_area * 0.45:
            continue

        # Popovers can be tall and narrow, or short and wider.
        compact = (
            (width <= 280 and height <= 540)
            or (width <= 430 and height <= 280)
        )
        if not compact:
            continue

        visible = [d for d in walk(node) if d.is_visible]
        if len(visible) < 3 or len(visible) > 70:
            continue

        named_content = [
            d
            for d in visible
            if d is not node
            and d.role in content_roles
            and (
                (d.name or "").strip()
                or (d.description or "").strip()
                or d.role in input_roles
            )
        ]

        if len(named_content) < 2:
            continue

        unique_names = {
            ((d.name or d.description or d.role) or "").strip()
            for d in named_content
            if ((d.name or d.description or d.role) or "").strip()
        }

        names_text = " ".join(unique_names).lower()

        strong_controls = [
            d
            for d in named_content
            if d.role in strong_control_roles
        ]

        inputs = [
            d
            for d in named_content
            if d.role in input_roles
        ]

        has_mode_overlay_controls = len(strong_controls) >= 2
        has_input = len(inputs) >= 1
        has_bit_options = "bit" in names_text
        has_place_options = "place" in names_text

        # Strong store/memory popover evidence.
        # A plain main-panel "Store" button is NOT enough.
        has_store_memory_hint = (
            "store value into existing or new variable" in names_text
            or "variable" in names_text
            or "rand" in names_text
            or "memory" in names_text
        )

        # Permanent calculator controls that often live in the right-side main panel.
        # If a compact container contains these controls but has no overlay-specific
        # evidence, it is probably part of the normal main UI, not a popover.
        main_control_hints = {
            "word size",
            "insert character",
            "shift right",
            "shift left",
            "superscript",
            "subscript",
            "factorize",
            "absolute value",
            "inverse",
            "exponent",
            "twos",
            "ones",
            "not",
            "and",
            "or",
            "xor",
        }

        has_main_panel_controls = any(
            hint in names_text
            for hint in main_control_hints
        )

        has_overlay_specific_hint = (
            has_mode_overlay_controls
            or has_input
            or has_bit_options
            or has_place_options
            or has_store_memory_hint
        )

        if has_main_panel_controls and not has_overlay_specific_hint:
            continue

        # Ordinary calculator grids often have many one-character names:
        # F, E, D, C, B, A, 9, 8, +, −, ×, etc.
        one_char_names = [
            n
            for n in unique_names
            if len(n.strip()) == 1
        ]
        one_char_ratio = len(one_char_names) / max(len(unique_names), 1)

        looks_like_plain_button_grid = (
            len(unique_names) >= 8
            and one_char_ratio >= 0.55
            and not has_overlay_specific_hint
        )

        if looks_like_plain_button_grid:
            continue

        # Large compact panels with many controls and no specific overlay hint
        # are likely normal UI groups, not foreground popovers.
        if len(unique_names) > 18 and not has_overlay_specific_hint:
            continue

        score = 0

        if has_mode_overlay_controls:
            score += 120

        if has_input:
            score += 90

        if has_bit_options:
            score += 100

        if has_place_options:
            score += 100

        if has_store_memory_hint:
            score += 100

        # Compact selector lists with meaningful multi-item labels.
        if len(unique_names) >= 3 and (
            has_bit_options
            or has_place_options
            or has_mode_overlay_controls
        ):
            score += 40

        # Store popover can have only 2 semantic named items.
        if len(unique_names) >= 2 and has_store_memory_hint:
            score += 40

        # Prefer smaller/deeper foreground containers.
        if width <= 160:
            score += 15

        if len(visible) <= 25:
            score += 15

        if score >= 90:
            candidates.append((score, node))

    # Choose best candidate:
    # 1. highest score;
    # 2. deeper subtree;
    # 3. smaller area.
    #
    # resolve_active_root uses popovers[-1], so sort ascending by these keys.
    candidates.sort(
        key=lambda item: (
            item[0],
            len(item[1].parent_path),
            -(
                item[1].bbox.width * item[1].bbox.height
                if item[1].bbox
                else 0
            ),
        )
    )

    return [node for _, node in candidates]


def resolve_active_root(root: A11YNode) -> ActiveRoot:
    """
    Resolve the active interaction root.

    Important:
    The last visible secondary/menu/popover root is treated as topmost because many GTK apps
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
        return ActiveRoot(
            node=node,
            kind="window_overlay",
            reason="visible popover-like control group is active overlay",
        )

    main_frame = _first_visible_frame(root)
    if main_frame is not None:
        return ActiveRoot(node=main_frame, kind="main", reason="no overlay found; using main frame")

    return ActiveRoot(node=root, kind="main", reason="no frame found; using application root")
