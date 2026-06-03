from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ui_explorer.core.actions import UIAction


class ActionKind(str, Enum):
    MACRO = "macro_candidate"
    MICRO = "micro_candidate"
    INPUT = "input_candidate"
    IGNORED = "ignored"


@dataclass(frozen=True)
class ClassifiedAction:
    action: UIAction
    kind: ActionKind
    priority: int
    reason: str

    def to_dict(self) -> dict:
        data = self.action.to_dict()
        data["kind"] = self.kind.value
        data["priority"] = self.priority
        data["reason"] = self.reason
        return data


MICRO_PUSH_NAMES = frozenset({
    # digits / common numeric buttons
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "a", "b", "c", "d", "e", "f",
    "A", "B", "C", "D", "E", "F",

    # arithmetic / symbols
    "+", "-", "−", "×", "÷", "/", "=", ".", ",", "(", ")", "%", "±",
    "π", "√", "^", "!",

    # common calculator-like operators; still generic enough to mark as content-changing
    "AND", "OR", "XOR", "NOT", "mod",
    "sin", "cos", "tan", "sinh", "cosh", "tanh",
    "log", "log₂", "ln",
    "frac", "int",
    "ones", "twos",
    "Absolute Value",
    "Exponent",
    "Factorial",
    "Factorize",
    "Inverse",
    "Square Root",

    # editing helpers usually change content, not macro structure
    "Undo",
    "Redo",
    "Clear",
    "Backspace",
})


MACRO_NAME_HINTS = (
    "menu",
    "mode",
    "preferences",
    "settings",
    "shortcuts",
    "about",
    "help",
    "format",
    "window",
    "size",
    "store",
    "insert",
    "open",
    "close",
    "cancel",
    "apply",
    "ok",
    "search",
)


WINDOW_CONTROL_NAMES = frozenset({
    "Close",
    "Minimize",
    "Maximize",
})


FORMAT_TOOLBAR_MICRO_TOGGLES = frozenset({
    "bold",
    "italic",
    "underline",
    "strikethrough",
    "superscript",
    "subscript",
    "shadow",
    "left",
    "center",
    "right",
    "justified",
    "align left",
    "align center",
    "align right",
    "justify",
    "formatting marks",
})


ROOT_DEFERRED_CONTROL_NAMES = frozenset({
    # Root toolbar/sidebar controls deferred from safe Writer exploration.
    "menu",
    "print preview",
    "hyperlink",
    "open",
    "bookmark",

    # These can expose panels/toolbars, but we deferred them during safe depth-2 mapping.
    "find and replace",
    "track changes functions",
})


SAFE_SUBMENU_NAMES = frozenset({
    # File
    "new",
    "recent documents",
    "templates",
    "export as",

    # Edit
    "paste special",
    "selection mode",
    "track changes",

    # View
    "toolbars",
    "rulers",
    "scrollbars",
    "grid and helplines",
    "zoom",

    # Insert
    "more breaks",

    # Format
    "text",
    "spacing",
    "align text",
    "lists",

    # Table
    "insert",
    "select",
    "size",
    "convert",

    # Tools
    "language",
    "autocorrect",
})


DEFERRED_SUBMENU_NAMES = frozenset({
    # File / external / security / wizard-like.
    "send",
    "digital signatures",
    "wizards",

    # Edit / content-object submenus.
    "comment",
    "reference",
    "object",

    # Insert / content or document-structure insertion.
    "media",
    "shape",
    "frame",
    "formatting mark",
    "footnote and endnote",
    "table of contents and index",
    "field",
    "header and footer",

    # Format / object-layout submenus.
    "image",
    "text box and shape",
    "frame and object",
    "anchor",
    "wrap",
    "arrange",
    "rotate or flip",
    "group",

    # Table / destructive or content-changing.
    "delete",

    # Form / fields.
    "more fields",

    # Tools / mutation, security, macro, or document update flows.
    "update",
    "protect document",
    "macros",
})


UNSAFE_MENU_ITEM_NAMES = frozenset({
    # File-system / document mutation / external side effects.
    "open...",
    "open remote...",
    "reload",
    "versions...",
    "save",
    "save as...",
    "save remote...",
    "save a copy...",
    "save all",
    "export...",
    "print...",
    "printer settings...",
    "preview in web browser",
    "send",
    "exit libreoffice",

    # Editing/content-changing actions.
    "undo",
    "redo",
    "repeat",
    "cut",
    "copy",
    "paste",
    "paste unformatted text",
    "paste special...",
    "paste as nested table",
    "paste as rows above",
    "paste as columns before",
    "select all",
    "select text",

    # Track changes/content operations.
    "record",
    "show",
    "manage...",
    "previous",
    "next",
    "accept",
    "accept and move to next",
    "accept all",
    "reject",
    "reject and move to next",
    "reject all",
    "comment...",
    "protect...",

    # Customization/profile mutation.
    "customize...",

    # Content/document-structure dialogs deferred manually.
    "bookmark...",
})


SAFE_CONTEXT_MENU_DIALOGS = frozenset({
    ("file", "properties..."),
    ("edit", "go to page..."),
    ("tools", "options..."),
    ("help", "about libreoffice"),
})


SAFE_CONTEXT_SUBMENUS = frozenset({
    ("language", "for selection"),
    ("language", "for paragraph"),
    ("language", "for all text"),
})


DIALOG_DEFERRED_BUTTON_NAMES = frozenset({
    "ok",
    "cancel",
    "help",
    "close",
    "apply",
})


def _parent_path_text(action: UIAction) -> str:
    return " / ".join(action.parent_path).lower()


def _is_inside_open_menu(action: UIAction) -> bool:
    return any(part.lower().startswith("menu/") for part in action.parent_path)


def _is_inside_dialog_or_alert(action: UIAction) -> bool:
    return any(
        part.lower().startswith(("dialog", "alert"))
        for part in action.parent_path
    )


def _is_formatting_toolbar_action(action: UIAction) -> bool:
    parent_text = _parent_path_text(action)
    return "tool bar/formatting" in parent_text or "toolbar/formatting" in parent_text


def _menu_context(action: UIAction) -> str:
    for part in reversed(action.parent_path):
        lower = part.lower()
        if lower.startswith("menu/"):
            return lower.split("/", 1)[1].strip()
    return ""


def _is_root_toolbar_or_sidebar_action(action: UIAction) -> bool:
    parent_text = _parent_path_text(action)
    return (
        "tool bar/" in parent_text
        or "toolbar/" in parent_text
        or "panel/properties" in parent_text
        or "sidebar" in parent_text
    )


def _is_top_menu_bar_action(action: UIAction) -> bool:
    return (
        action.role == "menu"
        and bool(action.parent_path)
        and action.parent_path[-1].lower() == "menu bar"
    )


def _looks_like_bit_cell(action: UIAction) -> bool:
    # GNOME Calculator bit-grid-like cells appear as tiny push buttons,
    # often with name "0" and description as bit index.
    x, y, w, h = action.bbox
    return action.role == "push button" and w <= 20 and h <= 35


def classify_action(action: UIAction) -> ClassifiedAction:
    role = action.role
    name = action.name.strip()
    name_lower = name.lower()

    if name in WINDOW_CONTROL_NAMES:
        return ClassifiedAction(
            action=action,
            kind=ActionKind.IGNORED,
            priority=100,
            reason="window control action is ignored for safe exploration",
        )

    if role in {"entry", "editbar", "spin button"}:
        return ClassifiedAction(
            action=action,
            kind=ActionKind.INPUT,
            priority=80,
            reason="editable/input-like control",
        )

    if role == "menu":
        if _is_top_menu_bar_action(action):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.MACRO,
                priority=12,
                reason="top-level menu bar item opens a navigation menu",
            )

        if _is_inside_open_menu(action):
            if name_lower in DEFERRED_SUBMENU_NAMES:
                return ClassifiedAction(
                    action=action,
                    kind=ActionKind.IGNORED,
                    priority=100,
                    reason="submenu deferred from safe exploration policy",
                )

            if (_menu_context(action), name_lower) in SAFE_CONTEXT_SUBMENUS:
                return ClassifiedAction(
                    action=action,
                    kind=ActionKind.MACRO,
                    priority=15,
                    reason="safe context submenu inside opened menu may reveal navigation structure",
                )

            if name_lower in SAFE_SUBMENU_NAMES:
                return ClassifiedAction(
                    action=action,
                    kind=ActionKind.MACRO,
                    priority=15,
                    reason="safe submenu inside opened menu may reveal navigation structure",
                )

            return ClassifiedAction(
                action=action,
                kind=ActionKind.MICRO,
                priority=90,
                reason="submenu inside opened menu is not selected for macro exploration by default",
            )

        return ClassifiedAction(
            action=action,
            kind=ActionKind.MACRO,
            priority=15,
            reason="visible menu may open or represent a navigation context",
        )

    if role in {"combo box", "tab", "tree item"}:
        return ClassifiedAction(
            action=action,
            kind=ActionKind.MACRO,
            priority=10,
            reason=f"{role} commonly opens or switches UI context",
        )

    if role == "menu item":
        if _is_inside_open_menu(action):
            if name_lower in UNSAFE_MENU_ITEM_NAMES:
                return ClassifiedAction(
                    action=action,
                    kind=ActionKind.IGNORED,
                    priority=100,
                    reason="unsafe/content-changing menu item ignored for safe exploration",
                )

            if (_menu_context(action), name_lower) in SAFE_CONTEXT_MENU_DIALOGS:
                return ClassifiedAction(
                    action=action,
                    kind=ActionKind.MACRO,
                    priority=25,
                    reason="safe menu item likely opens an inspectable dialog/navigation context",
                )

            return ClassifiedAction(
                action=action,
                kind=ActionKind.MICRO,
                priority=90,
                reason="menu item inside opened menu is not selected for macro exploration by default",
            )

        return ClassifiedAction(
            action=action,
            kind=ActionKind.MICRO,
            priority=90,
            reason="menu item outside opened menu is not selected for macro exploration by default",
        )

    if role in {"toggle button", "radio button", "check box"}:
        if _is_inside_dialog_or_alert(action):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.IGNORED,
                priority=100,
                reason="dialog control deferred from safe depth-3 exploration",
            )

        if (
            role == "toggle button"
            and _is_root_toolbar_or_sidebar_action(action)
            and name_lower in ROOT_DEFERRED_CONTROL_NAMES
        ):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.IGNORED,
                priority=100,
                reason="root toolbar/sidebar control deferred from safe exploration",
            )

        if role == "toggle button" and name_lower in FORMAT_TOOLBAR_MICRO_TOGGLES:
            return ClassifiedAction(
                action=action,
                kind=ActionKind.MICRO,
                priority=90,
                reason="formatting/content toggle changes document view/style, not navigation state",
            )

        if (
            role == "toggle button"
            and _is_formatting_toolbar_action(action)
            and name_lower in FORMAT_TOOLBAR_MICRO_TOGGLES
        ):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.MICRO,
                priority=90,
                reason="formatting toolbar toggle changes document style/content, not navigation state",
            )

        return ClassifiedAction(
            action=action,
            kind=ActionKind.MACRO,
            priority=20,
            reason=f"{role} may reveal, select, or switch UI structure",
        )

    if role == "push button":
        if _looks_like_bit_cell(action):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.MICRO,
                priority=90,
                reason="tiny push button looks like grid/cell content control",
            )

        if (
            _is_inside_dialog_or_alert(action)
            and name_lower in DIALOG_DEFERRED_BUTTON_NAMES
        ):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.IGNORED,
                priority=100,
                reason="dialog push button deferred from safe depth-3 exploration",
            )

        if (
            _is_root_toolbar_or_sidebar_action(action)
            and name_lower in ROOT_DEFERRED_CONTROL_NAMES
        ):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.IGNORED,
                priority=100,
                reason="root toolbar control deferred from safe exploration",
            )

        if name in MICRO_PUSH_NAMES or len(name) == 1:
            return ClassifiedAction(
                action=action,
                kind=ActionKind.MICRO,
                priority=90,
                reason="push button looks like value/operator/content action",
            )

        if any(hint in name_lower for hint in MACRO_NAME_HINTS):
            return ClassifiedAction(
                action=action,
                kind=ActionKind.MACRO,
                priority=30,
                reason="push button name suggests menu/dialog/navigation/context change",
            )

        # Conservative default: don't seed unknown push buttons as macro in MVP.
        # They are still visible in raw actions and can be enabled later.
        return ClassifiedAction(
            action=action,
            kind=ActionKind.MICRO,
            priority=95,
            reason="push button has no macro-context hint; treat as content action for MVP",
        )

    return ClassifiedAction(
        action=action,
        kind=ActionKind.IGNORED,
        priority=100,
        reason=f"role {role!r} is not part of macro exploration policy",
    )


def classify_actions(actions: list[UIAction]) -> list[ClassifiedAction]:
    return [classify_action(action) for action in actions]


def macro_actions(classified: list[ClassifiedAction]) -> list[ClassifiedAction]:
    return [item for item in classified if item.kind == ActionKind.MACRO]
