import json
from pathlib import Path

from ui_explorer.cli.build_agent_map import build_agent_map
from ui_explorer.cli.inspect_agent_map import (
    _find_in_item_index,
    _find_state_details,
    _state_summary,
)


def _write_xml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip(), encoding="utf-8")


def _write_graph(path: Path, graph: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph), encoding="utf-8")


def test_build_agent_map_uses_top_level_items_and_state_refs(tmp_path):
    maps_dir = tmp_path / "maps"
    app_dir = maps_dir / "calc"

    root_xml = app_dir / "states" / "root" / "a11y.xml"
    next_xml = app_dir / "states" / "next" / "a11y.xml"

    _write_xml(
        root_xml,
        """
        <element role="application" name="gnome-calculator" states="enabled,showing,visible">
          <element role="frame" name="Calculator" x="0" y="0" width="600" height="600" states="enabled,showing,visible">
            <element role="panel" name="" states="enabled,showing,visible">
              <element role="push button" name="Undo" description="Undo [Ctrl+Z]" x="10" y="4" width="68" height="46" states="enabled,sensitive,showing,visible"/>
              <element role="push button" name="Open" description="" x="1" y="2" width="30" height="40" states="enabled,sensitive,showing,visible"/>
              <element role="menu item" name="Hidden Hertz" description="" x="-2147483648" y="-2147483648" width="1" height="1" states="enabled,sensitive,visible"/>
            </element>
          </element>
        </element>
        """,
    )

    _write_xml(
        next_xml,
        """
        <element role="application" name="gnome-calculator" states="enabled,showing,visible">
          <element role="frame" name="Calculator" x="0" y="0" width="600" height="600" states="enabled,showing,visible">
            <element role="panel" name="" states="enabled,showing,visible">
              <element role="push button" name="Undo" description="Undo [Ctrl+Z]" x="10" y="4" width="68" height="46" states="enabled,sensitive,showing,visible"/>
            </element>
          </element>
        </element>
        """,
    )

    graph = {
        "schema_version": "1.0",
        "app_id": "calc",
        "root_state_id": "root",
        "nodes": {
            "root": {
                "state_id": "root",
                "status": "confirmed",
                "xml_path": str(root_xml),
                "active_root": {
                    "kind": "main",
                    "role": "frame",
                    "name": "Calculator",
                },
                "macro_hash": "root_macro",
                "content_hash": "root_content",
                "macro_action_count": 1,
                "visible_node_count": 4,
                "depth": 0,
                "label": "Calculator",
            },
            "next": {
                "state_id": "next",
                "status": "confirmed",
                "xml_path": str(next_xml),
                "active_root": {
                    "kind": "main",
                    "role": "frame",
                    "name": "Calculator",
                },
                "macro_hash": "next_macro",
                "content_hash": "next_content",
                "macro_action_count": 0,
                "visible_node_count": 3,
                "depth": 1,
                "label": "Calculator",
            },
        },
        "edges": {
            "root:open": {
                "edge_id": "root:open",
                "from_state": "root",
                "action_key": "open",
                "action": {
                    "action_key": "open",
                    "role": "push button",
                    "name": "Open",
                    "description": "",
                    "states": ["enabled", "sensitive", "showing", "visible"],
                    "bbox": [1, 2, 30, 40],
                    "parent_path": [],
                    "depth": 4,
                },
                "status": "confirmed",
                "to_state": "next",
                "priority": 20,
                "attempts": 1,
                "reason": "test",
                "observed": {
                    "kind": "new_macro_state",
                    "to_state": "next",
                    "macro_changed": True,
                    "content_changed": True,
                    "reason": "test",
                },
                "created_order": 0,
            }
        },
        "completion": {
            "status": "complete",
            "pending_edges": 0,
            "reason": "no_pending_edges",
        },
    }

    _write_graph(app_dir / "graph.json", graph)

    agent_map = build_agent_map(app="calc", maps_dir=maps_dir)

    assert agent_map["schema_version"] == "1.2"
    assert "incoming_actions" in agent_map["states"]["root"]
    assert "delta_observed_items" in agent_map["states"]["next"]
    assert agent_map["states"]["next"]["delta_base_state"] == "root"
    assert agent_map["summary"]["states"] == 2
    assert agent_map["summary"]["edges"] == 1
    assert "items" in agent_map
    assert "verified_action_index" in agent_map

    # "Undo" appears in both states but full definition is stored once.
    undo_items = [
        item
        for item in agent_map["items"].values()
        if item["role"] == "push button" and item["name"] == "Undo"
    ]
    assert len(undo_items) == 1

    undo_ref = undo_items[0]["item_id"]

    assert agent_map["states"]["root"]["observed_items"] == [
        {
            "ref": undo_ref,
            "role": "push button",
            "name": "Undo",
            "description": "Undo [Ctrl+Z]",
        }
    ]

    assert agent_map["states"]["next"]["observed_items"] == [
        {
            "ref": undo_ref,
            "role": "push button",
            "name": "Undo",
            "description": "Undo [Ctrl+Z]",
        }
    ]

    # State-local observed item is only a ref-preview, not full repeated object.
    observed_ref = agent_map["states"]["root"]["observed_items"][0]
    assert "states" not in observed_ref
    assert "parent_path_tail" not in observed_ref
    assert "visible_bbox_hint" not in observed_ref
    assert "status" not in observed_ref

    # Full observed item details are in top-level items.
    full_undo = agent_map["items"][undo_ref]
    assert full_undo["states"] == ["enabled", "sensitive", "showing", "visible"]
    assert full_undo["visible_bbox_hint"] == [10, 4, 68, 46]

    # Hidden/non-showing A11Y model item should not enter observed items.
    all_item_names = [item["name"] for item in agent_map["items"].values()]
    assert "Hidden Hertz" not in all_item_names

    # Verified action is excluded from observed_items and stays inline as executable transition.
    assert len(agent_map["states"]["root"]["verified_actions"]) == 1
    verified = agent_map["states"]["root"]["verified_actions"][0]
    assert verified["name"] == "Open"
    assert verified["status"] == "verified"
    assert verified["edge_status"] == "confirmed"
    assert verified["to_state"] == "next"
    assert verified["bbox"] == [1, 2, 30, 40]

    root_observed_names = [
        item["name"]
        for item in agent_map["states"]["root"]["observed_items"]
    ]
    assert "Open" not in root_observed_names


def test_build_agent_map_item_index_counts_verified_and_observed_refs(tmp_path):
    maps_dir = tmp_path / "maps"
    app_dir = maps_dir / "calc"

    root_xml = app_dir / "states" / "root" / "a11y.xml"

    _write_xml(
        root_xml,
        """
        <element role="application" name="gnome-calculator" states="enabled,showing,visible">
          <element role="frame" name="Calculator" x="0" y="0" width="600" height="600" states="enabled,showing,visible">
            <element role="panel" name="" states="enabled,showing,visible">
              <element role="push button" name="AND" description="Boolean AND" x="10" y="10" width="50" height="30" states="enabled,sensitive,showing,visible"/>
            </element>
          </element>
        </element>
        """,
    )

    graph = {
        "schema_version": "1.0",
        "app_id": "calc",
        "root_state_id": "root",
        "nodes": {
            "root": {
                "state_id": "root",
                "status": "confirmed",
                "xml_path": str(root_xml),
                "active_root": {
                    "kind": "main",
                    "role": "frame",
                    "name": "Calculator",
                },
                "macro_hash": "root_macro",
                "content_hash": "root_content",
                "macro_action_count": 0,
                "visible_node_count": 2,
                "depth": 0,
                "label": "Calculator",
            },
        },
        "edges": {},
        "completion": {
            "status": "complete",
            "pending_edges": 0,
            "reason": "no_pending_edges",
        },
    }

    _write_graph(app_dir / "graph.json", graph)

    agent_map = build_agent_map(app="calc", maps_dir=maps_dir)

    assert agent_map["summary"]["items"] == 1
    assert agent_map["summary"]["observed_item_refs"] == 1

    matches = [
        item
        for item in agent_map["item_index"].values()
        if item["name"] == "AND" and item["role"] == "push button"
    ]

    assert len(matches) == 1
    assert matches[0]["occurrences"] == 1
    assert matches[0]["verified_action_count"] == 0
    assert matches[0]["observed_item_count"] == 1
    assert matches[0]["states"] == ["root"]
    assert matches[0]["statuses"] == ["observed_unverified"]


def test_inspect_agent_map_resolves_refs_for_state_and_details():
    agent_map = {
        "schema_version": "1.1",
        "app_id": "calc",
        "root_state_id": "root",
        "summary": {},
        "items": {
            "item-and": {
                "item_id": "item-and",
                "role": "push button",
                "name": "AND",
                "description": "Boolean AND",
                "status": "observed_unverified",
                "states": ["enabled", "sensitive", "showing", "visible"],
                "parent_path_tail": ["panel"],
                "visible_bbox_hint": [10, 10, 50, 30],
            }
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
                        "edge_id": "root:mode",
                        "role": "toggle button",
                        "name": "Mode selection",
                        "description": "",
                        "status": "verified",
                        "method": "bbox_click",
                        "to_state": "mode",
                        "bbox": [1, 2, 30, 40],
                    }
                ],
                "observed_items": [
                    {
                        "ref": "item-and",
                        "role": "push button",
                        "name": "AND",
                        "description": "Boolean AND",
                    }
                ],
            }
        },
        "item_index": {
            "idx-and": {
                "name": "AND",
                "role": "push button",
                "states": ["root"],
                "occurrences": 1,
                "verified_action_count": 0,
                "observed_item_count": 1,
                "statuses": ["observed_unverified"],
            },
            "idx-mode": {
                "name": "Mode selection",
                "role": "toggle button",
                "states": ["root"],
                "occurrences": 1,
                "verified_action_count": 1,
                "observed_item_count": 0,
                "statuses": ["verified"],
            },
        },
    }

    state_summary = _state_summary(agent_map, "root", limit=10)

    assert state_summary["ok"] is True
    assert state_summary["observed_items_total"] == 1
    assert state_summary["observed_items_preview"][0]["item_id"] == "item-and"
    assert state_summary["observed_items_preview"][0]["name"] == "AND"
    assert state_summary["observed_items_preview"][0]["status"] == "observed_unverified"
    assert state_summary["observed_items_preview"][0]["parent_path_tail"] == ["panel"]
    assert state_summary["observed_items_preview"][0]["has_visible_bbox_hint"] is True

    details = _find_state_details(
        agent_map,
        "AND",
        exact=True,
        limit=5,
    )

    assert len(details) == 1
    assert details[0]["section"] == "observed_items"
    assert details[0]["state_id"] == "root"
    assert details[0]["item"]["item_id"] == "item-and"
    assert details[0]["item"]["visible_bbox_hint"] == [10, 10, 50, 30]

    matches = _find_in_item_index(agent_map, "AND", exact=True)

    assert len(matches) == 1
    assert matches[0]["name"] == "AND"
    assert matches[0]["observed_item_count"] == 1
    assert matches[0]["state_count"] == 1


def test_inspect_agent_map_supports_verified_action_search():
    agent_map = {
        "schema_version": "1.1",
        "app_id": "calc",
        "root_state_id": "root",
        "summary": {},
        "items": {},
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
                        "edge_id": "root:mode",
                        "role": "toggle button",
                        "name": "Mode selection",
                        "description": "",
                        "status": "verified",
                        "method": "bbox_click",
                        "to_state": "mode",
                        "bbox": [1, 2, 30, 40],
                    }
                ],
                "observed_items": [],
            }
        },
        "item_index": {
            "idx-mode": {
                "name": "Mode selection",
                "role": "toggle button",
                "states": ["root"],
                "occurrences": 1,
                "verified_action_count": 1,
                "observed_item_count": 0,
                "statuses": ["verified"],
            }
        },
    }

    details = _find_state_details(
        agent_map,
        "Mode selection",
        exact=True,
        limit=5,
    )

    assert len(details) == 1
    assert details[0]["section"] == "verified_actions"
    assert details[0]["item"]["edge_id"] == "root:mode"

    matches = _find_in_item_index(
        agent_map,
        "Mode selection",
        exact=True,
    )

    assert len(matches) == 1
    assert matches[0]["verified_action_count"] == 1
    assert matches[0]["observed_item_count"] == 0
