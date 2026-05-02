from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.actions import extract_actions
from ui_explorer.core.a11y_parser import parse_a11y_xml


MODE_POPOVER_XML = Path("tests/fixtures/a11y/calc_mode_popover.xml")


def test_mode_popover_active_root_is_overlay():
    assert MODE_POPOVER_XML.exists(), "Create tests/fixtures/a11y/calc_mode_popover.xml first."

    root = parse_a11y_xml(MODE_POPOVER_XML)
    active = resolve_active_root(root)

    assert active.kind in {"menu", "window_overlay"}
    assert active.node.role != "frame"

    actions = extract_actions(active.node)
    names = {a.name for a in actions}

    assert {"Basic", "Advanced", "Financial", "Programming", "Keyboard"} <= names
    assert "Primary menu" not in names
