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
