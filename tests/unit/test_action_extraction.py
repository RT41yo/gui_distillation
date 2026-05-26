from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.actions import extract_actions
from ui_explorer.core.a11y_parser import parse_a11y_xml


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def test_extract_actions_from_active_root():
    assert FIXTURE.exists(), "Run capture CLI first to create the A11Y XML fixture."

    root = parse_a11y_xml(FIXTURE)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)

    assert len(actions) > 0
    assert all(action.action_key for action in actions)
    assert all(len(action.action_key) == 16 for action in actions)


def test_action_keys_are_unique_for_state():
    root = parse_a11y_xml(FIXTURE)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    keys = [action.action_key for action in actions]

    assert len(keys) == len(set(keys))


def test_known_calculator_actions_present():
    root = parse_a11y_xml(FIXTURE)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    names = {action.name for action in actions}

    assert "Mode selection" in names
    assert "Primary menu" in names


def test_libreoffice_writer_top_menu_actions_present():
    path = Path("tests/fixtures/a11y/writer/root_pos_a.xml")
    assert path.exists(), "Run Writer capture first."

    root = parse_a11y_xml(path)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    names = {a.name for a in actions}

    assert {"File", "Edit", "View", "Insert", "Format", "Tools", "Help"} <= names


def test_libreoffice_writer_top_menu_actions_are_deduplicated():
    path = Path("tests/fixtures/a11y/writer/root_pos_a.xml")
    assert path.exists(), "Run Writer capture first."

    root = parse_a11y_xml(path)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)

    top_menu_names = [
        action.name
        for action in actions
        if action.role == "menu" and "menu bar" in " / ".join(action.parent_path).lower()
    ]

    assert top_menu_names.count("File") == 1
    assert top_menu_names.count("Edit") == 1
    assert top_menu_names.count("Help") == 1
    assert {"File", "Edit", "View", "Insert", "Format", "Tools", "Help"} <= set(top_menu_names)

def test_libreoffice_writer_open_file_menu_actions_present():
    path = Path("tests/fixtures/a11y/writer/file_menu_open.xml")
    assert path.exists()

    root = parse_a11y_xml(path)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)
    names = {a.name for a in actions}

    assert {"New", "Open...", "Save", "Save As...", "Export...", "Print...", "Exit LibreOffice"} <= names

