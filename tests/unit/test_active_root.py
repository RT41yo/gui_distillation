from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.a11y_parser import parse_a11y_xml


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def test_active_root_for_main_window_is_frame():
    assert FIXTURE.exists(), "Run capture CLI first to create the A11Y XML fixture."

    root = parse_a11y_xml(FIXTURE)
    active = resolve_active_root(root)

    assert active.kind == "main"
    assert active.node.role == "frame"
    assert active.node.is_visible
