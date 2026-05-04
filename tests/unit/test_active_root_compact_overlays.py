from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.actions import extract_actions
from ui_explorer.core.a11y_parser import parse_a11y_xml


def names_from(xml_path: str) -> set[str]:
    root = parse_a11y_xml(Path(xml_path))
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    return active.kind, {a.name for a in actions}


def test_word_size_popover_is_window_overlay():
    kind, names = names_from("tests/fixtures/a11y/calc_word_size_popover.xml")

    assert kind == "window_overlay"
    assert {"64-bit", "32-bit", "16-bit", "8-bit"} & names


def test_store_popover_is_window_overlay():
    root = parse_a11y_xml(Path("tests/fixtures/a11y/calc_store_popover.xml"))
    active = resolve_active_root(root)

    assert active.kind == "window_overlay"
    assert active.node.role != "frame"


def test_shift_right_popover_is_window_overlay():
    kind, names = names_from("tests/fixtures/a11y/calc_shift_right_popover.xml")

    assert kind == "window_overlay"
    assert any("place" in name for name in names)


def test_shift_left_popover_is_window_overlay():
    kind, names = names_from("tests/fixtures/a11y/calc_shift_left_popover.xml")

    assert kind == "window_overlay"
    assert any("place" in name for name in names)


def test_superscript_toggle_remains_main():
    root = parse_a11y_xml(Path("tests/fixtures/a11y/calc_superscript_toggle.xml"))
    active = resolve_active_root(root)

    assert active.kind == "main"


def test_subscript_toggle_remains_main():
    root = parse_a11y_xml(Path("tests/fixtures/a11y/calc_subscript_toggle.xml"))
    active = resolve_active_root(root)

    assert active.kind == "main"
