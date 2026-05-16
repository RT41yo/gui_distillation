from __future__ import annotations

from ui_explorer.cli.inspect_agent_map import (
    _find_in_item_index,
    _find_state_details,
    _state_summary,
)


def _fake_agent_map():
    return {
        "app_id": "calc",
        "root_state_id": "root",
        "item_index": {
            "hertz_id": {
                "name": "Hertz",
                "role": "menu item",
                "states": ["root", "frequency_state"],
                "occurrences": 2,
                "verified_action_count": 0,
                "observed_item_count": 2,
                "statuses": ["observed_unverified"],
            },
            "kilohertz_id": {
                "name": "Kilohertz",
                "role": "menu item",
                "states": ["root"],
                "occurrences": 1,
                "verified_action_count": 0,
                "observed_item_count": 1,
                "statuses": ["observed_unverified"],
            },
            "decimal_id": {
                "name": "Decimal",
                "role": "combo box",
                "states": ["root"],
                "occurrences": 1,
                "verified_action_count": 1,
                "observed_item_count": 0,
                "statuses": ["verified"],
            },
        },
        "states": {
            "root": {
                "state_id": "root",
                "label": "Calculator",
                "depth": 0,
                "active_root": {
                    "kind": "main",
                    "role": "frame",
                    "name": "Calculator",
                },
                "verified_actions": [
                    {
                        "edge_id": "root:decimal",
                        "role": "combo box",
                        "name": "Decimal",
                        "description": "",
                        "status": "verified",
                        "method": "bbox_click",
                        "bbox": [1, 2, 3, 4],
                        "to_state": "decimal_menu",
                    }
                ],
                "observed_items": [
                    {
                        "item_id": "hertz_occurrence",
                        "role": "menu item",
                        "name": "Hertz",
                        "description": "",
                        "status": "observed_unverified",
                        "states": ["enabled", "visible"],
                        "parent_path_tail": [
                            "combo box",
                            "menu",
                            "menu/Frequency",
                        ],
                    },
                    {
                        "item_id": "kilohertz_occurrence",
                        "role": "menu item",
                        "name": "Kilohertz",
                        "description": "",
                        "status": "observed_unverified",
                        "states": ["enabled", "visible"],
                        "parent_path_tail": [
                            "combo box",
                            "menu",
                            "menu/Frequency",
                        ],
                    },
                ],
            },
            "frequency_state": {
                "state_id": "frequency_state",
                "label": "Frequency",
                "depth": 1,
                "active_root": {
                    "kind": "menu",
                    "role": "menu",
                    "name": "Frequency",
                },
                "verified_actions": [],
                "observed_items": [
                    {
                        "item_id": "hertz_occurrence_2",
                        "role": "menu item",
                        "name": "Hertz",
                        "description": "",
                        "status": "observed_unverified",
                        "states": ["enabled", "visible"],
                        "parent_path_tail": [
                            "menu",
                            "menu/Frequency",
                        ],
                    }
                ],
            },
        },
    }


def test_find_in_item_index_substring_query_matches_related_items():
    agent_map = _fake_agent_map()

    matches = _find_in_item_index(
        agent_map,
        "Hertz",
        exact=False,
    )

    names = {item["name"] for item in matches}

    assert names == {"Hertz", "Kilohertz"}


def test_find_in_item_index_exact_query_matches_only_exact_item():
    agent_map = _fake_agent_map()

    matches = _find_in_item_index(
        agent_map,
        "Hertz",
        exact=True,
    )

    assert len(matches) == 1
    assert matches[0]["name"] == "Hertz"
    assert matches[0]["verified_action_count"] == 0
    assert matches[0]["observed_item_count"] == 2
    assert matches[0]["statuses"] == ["observed_unverified"]


def test_find_in_item_index_prioritizes_verified_actions():
    agent_map = _fake_agent_map()

    matches = _find_in_item_index(
        agent_map,
        "Decimal",
        exact=True,
    )

    assert len(matches) == 1
    assert matches[0]["name"] == "Decimal"
    assert matches[0]["verified_action_count"] == 1
    assert matches[0]["observed_item_count"] == 0
    assert matches[0]["statuses"] == ["verified"]


def test_find_state_details_returns_matching_items():
    agent_map = _fake_agent_map()

    details = _find_state_details(
        agent_map,
        "Hertz",
        exact=True,
        limit=10,
    )

    assert len(details) == 2

    assert details[0]["state_id"] == "root"
    assert details[0]["section"] == "observed_items"
    assert details[0]["item"]["name"] == "Hertz"

    assert details[1]["state_id"] == "frequency_state"
    assert details[1]["section"] == "observed_items"
    assert details[1]["item"]["name"] == "Hertz"


def test_state_summary_for_existing_state():
    agent_map = _fake_agent_map()

    summary = _state_summary(agent_map, "root")

    assert summary["ok"] is True
    assert summary["state_id"] == "root"
    assert summary["label"] == "Calculator"
    assert summary["depth"] == 0
    assert len(summary["verified_actions"]) == 1
    assert summary["verified_actions"][0]["name"] == "Decimal"
    assert summary["verified_actions"][0]["has_bbox"] is True
    assert summary["observed_items_total"] == 2


def test_state_summary_for_missing_state():
    agent_map = _fake_agent_map()

    summary = _state_summary(agent_map, "missing")

    assert summary["ok"] is False
    assert "state not found" in summary["error"]
