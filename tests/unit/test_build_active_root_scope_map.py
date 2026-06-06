from __future__ import annotations

from pathlib import Path

from ui_explorer.cli.build_active_root_scope_map import build_active_root_scope_map
from ui_explorer.core.a11y_parser import parse_a11y_xml
from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.actions import extract_actions
from ui_explorer.graph.models import EdgeStatus
from ui_explorer.graph.store import GraphStore


CALC_FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")
WRITER_FILE_MENU = Path("tests/fixtures/a11y/writer/file_menu_open.xml")


def test_build_active_root_scope_map_from_existing_graph(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=CALC_FIXTURE,
    )

    edge = next(iter(graph.edges.values()))
    edge.status = EdgeStatus.CONFIRMED
    edge.to_state = graph.root_state_id
    edge.reason = "test confirmed edge"

    store.save(graph)

    scope_map = build_active_root_scope_map(
        app="calc",
        maps_dir=maps_dir,
    )

    assert scope_map["schema_version"] == "1.0"
    assert scope_map["kind"] == "ui_explorer_active_root_scope_map"
    assert scope_map["app_id"] == "calc"
    assert scope_map["root_state_id"] == graph.root_state_id
    assert scope_map["summary"]["states"] == 1
    assert scope_map["summary"]["active_root_actions"] > 0
    assert scope_map["summary"]["active_root_mismatch_count"] == 0

    root_state = scope_map["states"][graph.root_state_id]
    assert root_state["active_root_matches_graph"] is True
    assert root_state["recomputed_active_root"]["name"] == "Calculator"
    assert root_state["active_root_actions"]
    assert root_state["active_root_micro_actions"] or root_state["active_root_input_actions"]

    first_action = root_state["active_root_actions"][0]
    assert "kind" in first_action
    assert "priority" in first_action
    assert "reason" in first_action
    assert "has_visible_bbox" in first_action
    assert "is_showing" in first_action
    assert "is_sensitive" in first_action
    assert "is_enabled" in first_action


def test_active_root_scope_excludes_background_toolbar_for_open_menu(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="libreoffice_writer",
        xml_path=WRITER_FILE_MENU,
    )
    store.save(graph)

    scope_map = build_active_root_scope_map(
        app="libreoffice_writer",
        maps_dir=maps_dir,
    )

    state = next(iter(scope_map["states"].values()))
    assert state["recomputed_active_root"]["kind"] == "menu"
    assert state["recomputed_active_root"]["name"] == "File"

    action_names = {action["name"] for action in state["active_root_actions"]}
    assert "Bold" not in action_names
    assert "Open..." in action_names or "Save" in action_names


def test_active_root_match_uses_graph_and_recomputed_payload():
    root = parse_a11y_xml(WRITER_FILE_MENU)
    active = resolve_active_root(root)
    actions = extract_actions(active.node)

    assert active.kind == "menu"
    assert active.node.name == "File"
    assert actions
    assert all(action.name != "Bold" for action in actions)
