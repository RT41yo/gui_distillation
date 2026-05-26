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
    "select all",
    "select text",

    # Track changes/content operations.
    "accept",
    "accept all",
    "reject",
    "reject all",
    "accept and move to next",
    "reject and move to next",
})


SAFE_MENU_DIALOG_NAMES = frozenset({
    # Relatively safe dialogs/inspectors/navigation panels.
    "properties...",
    "find...",
    "find and replace...",
    "go to page...",
    "hyperlink...",
    "bookmark...",
    "options...",
    "customize...",
    "extensions...",
    "about libreoffice",
})


def _is_inside_open_menu(action: UIAction) -> bool:
    return any(part.lower().startswith("menu/") for part in action.parent_path)


def _parent_path_text(action: UIAction) -> str:
    return " / ".join(action.parent_path).lower()


def _is_formatting_toolbar_action(action: UIAction) -> bool:
    parent_text = _parent_path_text(action)
    return "tool bar/formatting" in parent_text or "toolbar/formatting" in parent_text


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


    if role in {"menu item"}:
        if _is_inside_open_menu(action):
            if name_lower in UNSAFE_MENU_ITEM_NAMES:
                return ClassifiedAction(
                    action=action,
                    kind=ActionKind.IGNORED,
                    priority=100,
                    reason="unsafe or content-changing menu item ignored for safe exploration",
                )

            if name_lower in SAFE_MENU_DIALOG_NAMES:
                return ClassifiedAction(
                    action=action,
                    kind=ActionKind.MACRO,
                    priority=25,
                    reason="safe menu item likely opens an inspectable dialog/navigation context",
                )

            # Conservative default inside opened menus:
            # do not expand arbitrary menu items unless explicitly allowed.
            return ClassifiedAction(
                action=action,
                kind=ActionKind.MICRO,
                priority=90,
                reason="menu item inside opened menu is not selected for macro exploration by default",
            )

        return ClassifiedAction(
            action=action,
            kind=ActionKind.MACRO,
            priority=15,
            reason="menu item may navigate, open a dialog, or change UI context",
        )

    if role in {"toggle button", "radio button", "check box"}:
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
