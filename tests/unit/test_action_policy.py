from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.action_policy import ActionKind, classify_actions
from ui_explorer.core.actions import extract_actions
from ui_explorer.core.a11y_parser import parse_a11y_xml


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def _classified():
    root = parse_a11y_xml(FIXTURE)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    return classify_actions(actions)


def test_macro_actions_include_known_context_controls():
    items = _classified()
    macro_names = {item.action.name for item in items if item.kind == ActionKind.MACRO}

    assert "Mode selection" in macro_names
    assert "Primary menu" in macro_names

    assert (
        {"Decimal", "Word Size"} & macro_names
        or {"Degrees", "Radians"} <= macro_names
    )


def test_micro_actions_include_undo_and_bit_cells():
    items = _classified()
    undo = [item for item in items if item.action.name == "Undo"]

    assert undo
    assert undo[0].kind == ActionKind.MICRO


def test_macro_count_is_less_than_raw_count():
    items = _classified()
    macro = [item for item in items if item.kind == ActionKind.MACRO]

    assert len(macro) > 0
    assert len(macro) < len(items)


def test_libreoffice_writer_top_menus_are_macro_actions():
    path = Path("tests/fixtures/a11y/writer/root_pos_a.xml")
    assert path.exists(), "Run Writer capture first."

    root = parse_a11y_xml(path)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    classified = classify_actions(actions)

    macro_names = {item.action.name for item in classified if item.kind == ActionKind.MACRO}

    assert {"File", "Edit", "View", "Insert", "Format", "Tools", "Help"} <= macro_names


def test_libreoffice_writer_formatting_toggles_are_micro():
    path = Path("tests/fixtures/a11y/writer/root_pos_a.xml")
    assert path.exists(), "Run Writer capture first."

    root = parse_a11y_xml(path)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    classified = classify_actions(actions)

    by_name = {item.action.name: item for item in classified}

    assert by_name["Bold"].kind == ActionKind.MICRO
    assert by_name["Italic"].kind == ActionKind.MICRO
    assert by_name["Left"].kind == ActionKind.MICRO
    assert by_name["Center"].kind == ActionKind.MICRO
    assert by_name["Right"].kind == ActionKind.MICRO


def test_libreoffice_writer_top_menus_remain_macro():
    path = Path("tests/fixtures/a11y/writer/root_pos_a.xml")
    assert path.exists(), "Run Writer capture first."

    root = parse_a11y_xml(path)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    classified = classify_actions(actions)

    macro_names = {item.action.name for item in classified if item.kind == ActionKind.MACRO}

    assert {"File", "Edit", "View", "Insert", "Format", "Tools", "Help"} <= macro_names

