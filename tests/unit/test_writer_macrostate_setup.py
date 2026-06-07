from __future__ import annotations

import pytest

from ui_explorer.synthetic.scope_index import ScopeIndex
from ui_explorer.synthetic.writer_macrostate_setup import (
    build_active_root_selector,
    build_navigation_steps,
    build_writer_macrostate_preflight,
    find_navigation_path,
)


@pytest.fixture(scope="module")
def scope_index() -> ScopeIndex:
    return ScopeIndex.load()


def test_find_navigation_path_for_root_is_empty(scope_index: ScopeIndex) -> None:
    root = scope_index.agent_map["root_state_id"]
    assert find_navigation_path(
        scope_index.agent_states,
        root_state_id=root,
        target_state_id=root,
    ) == []


def test_find_navigation_path_for_depth_one_state(scope_index: ScopeIndex) -> None:
    root = scope_index.agent_map["root_state_id"]
    path = find_navigation_path(
        scope_index.agent_states,
        root_state_id=root,
        target_state_id="2e0335a47afa",
    )
    assert len(path) == 1
    assert path[0]["name"] == "Edit"


def test_build_active_root_selector_for_menu_state(scope_index: ScopeIndex) -> None:
    scope_state = scope_index.get_scope_state("014013af658a")
    selector = build_active_root_selector(scope_state)
    assert selector["role"] == "menu"
    assert selector["name"] == "For All Text"
    assert selector["require_bbox"] is True
    assert selector["states"] == {"showing": True, "visible": True}


def test_build_writer_macrostate_preflight_for_root(scope_index: ScopeIndex) -> None:
    root = scope_index.agent_map["root_state_id"]
    block, provenance = build_writer_macrostate_preflight(
        scope_index,
        macro_state_id=root,
        vm_document_path="/home/user/Desktop/synthetic_writer_test.docx",
    )
    assert block is not None
    assert block["type"] == "a11y_preflight"
    assert provenance["status"] == "ready"
    assert provenance["navigation_edge_count"] == 0
    assert block["parameters"]["steps"][0]["op"] == "wait_for"


def test_build_writer_macrostate_preflight_for_depth_three(scope_index: ScopeIndex) -> None:
    block, provenance = build_writer_macrostate_preflight(
        scope_index,
        macro_state_id="014013af658a",
        vm_document_path="/home/user/Desktop/synthetic_writer_test.docx",
    )
    assert block is not None
    assert provenance["status"] == "ready"
    assert provenance["navigation_edge_count"] == 3
    ops = [step["op"] for step in block["parameters"]["steps"]]
    assert "click" in ops
    assert "move" in ops
    assert ops[-1] == "assert"


def test_build_navigation_steps_emits_click_and_sleep() -> None:
    steps = build_navigation_steps(
        [
            {"bbox": [10, 20, 30, 40], "edge_id": "e1", "role": "menu", "name": "View"},
            {"bbox": [50, 60, 30, 40], "edge_id": "e2", "role": "menu", "name": "Zoom"},
        ]
    )
    assert steps == [
        {
            "op": "click",
            "selector": {
                "require_bbox": True,
                "states": {"showing": True, "visible": True},
                "role": "menu",
                "name": "View",
            },
            "meta": {"edge_id": "e1", "role": "menu", "name": "View", "recorded_bbox": [10, 20, 30, 40]},
        },
        {"op": "sleep", "seconds": 0.8},
        {
            "op": "move",
            "selector": {
                "require_bbox": True,
                "states": {"showing": True, "visible": True},
                "role": "menu",
                "name": "Zoom",
            },
            "meta": {"edge_id": "e2", "role": "menu", "name": "Zoom", "recorded_bbox": [50, 60, 30, 40]},
        },
        {"op": "sleep", "seconds": 0.8},
    ]


def test_build_navigation_steps_clicks_final_dialog_edge() -> None:
    steps = build_navigation_steps(
        [
            {"bbox": [10, 20, 30, 40], "edge_id": "e1", "role": "menu", "name": "Help"},
            {"bbox": [50, 60, 30, 40], "edge_id": "e2", "role": "menu item", "name": "About LibreOffice"},
        ],
        target_active_root_kind="dialog",
    )
    assert [step["op"] for step in steps] == ["click", "sleep", "click", "sleep"]
