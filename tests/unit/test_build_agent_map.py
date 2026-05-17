from __future__ import annotations

from pathlib import Path

from ui_explorer.cli.build_agent_map import build_agent_map
from ui_explorer.graph.models import EdgeStatus
from ui_explorer.graph.store import GraphStore


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def test_build_agent_map_from_existing_graph(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=FIXTURE,
    )

    edge = next(iter(graph.edges.values()))
    edge.status = EdgeStatus.CONFIRMED
    edge.to_state = graph.root_state_id
    edge.reason = "test confirmed edge"

    store.save(graph)

    agent_map = build_agent_map(
        app="calc",
        maps_dir=maps_dir,
    )

    assert agent_map["schema_version"] == "1.2"
    assert agent_map["kind"] == "ui_explorer_agent_map"
    assert agent_map["app_id"] == "calc"
    assert agent_map["root_state_id"] == graph.root_state_id

    assert agent_map["summary"]["states"] == 1
    assert agent_map["summary"]["edges"] == len(graph.edges)
    assert agent_map["summary"]["pending_edges"] == len(graph.edges) - 1
    assert agent_map["summary"]["items"] == len(agent_map["items"])
    assert agent_map["summary"]["observed_item_refs"] == sum(
        len(state.get("observed_items", []))
        for state in agent_map["states"].values()
    )
    assert agent_map["summary"]["delta_observed_item_refs"] == sum(
        len(state.get("delta_observed_items", []))
        for state in agent_map["states"].values()
    )

    assert "usage_notes" in agent_map
    assert "states" in agent_map
    assert "items" in agent_map
    assert "item_index" in agent_map
    assert "verified_action_index" in agent_map

    root_state = agent_map["states"][graph.root_state_id]

    assert root_state["state_id"] == graph.root_state_id
    assert root_state["depth"] == 0
    assert root_state["active_root"]["name"] == "Calculator"

    assert "incoming_actions" in root_state
    assert "delta_base_state" in root_state
    assert "delta_observed_items" in root_state

    assert root_state["delta_base_state"] is None
    assert root_state["delta_observed_items"] == []

    verified = root_state["verified_actions"]
    assert len(verified) == 1

    verified_action = verified[0]
    assert verified_action["status"] == "verified"
    assert verified_action["method"] == "bbox_click"
    assert verified_action["edge_status"] == "confirmed"
    assert verified_action["to_state"] == graph.root_state_id
    assert "bbox" in verified_action
    assert len(verified_action["bbox"]) == 4


def test_observed_items_are_refs_and_do_not_expose_bbox_inline(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=FIXTURE,
    )

    store.save(graph)

    agent_map = build_agent_map(
        app="calc",
        maps_dir=maps_dir,
    )

    observed_total = 0

    for state in agent_map["states"].values():
        for item in state.get("observed_items", []):
            observed_total += 1

            # Schema 1.2: state-local observed_items are short refs only.
            assert "ref" in item
            assert item["ref"] in agent_map["items"]

            assert "role" in item
            assert "name" in item
            assert "description" in item

            # Full observed-only fields must not be repeated inline in states.
            assert "status" not in item
            assert "states" not in item
            assert "parent_path_tail" not in item
            assert "visible_bbox_hint" not in item
            assert "bbox" not in item

            full_item = agent_map["items"][item["ref"]]

            assert full_item["status"] == "observed_unverified"
            assert "bbox" not in full_item

    assert observed_total > 0


def test_delta_observed_items_are_refs_and_do_not_expose_bbox_inline(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=FIXTURE,
    )

    store.save(graph)

    agent_map = build_agent_map(
        app="calc",
        maps_dir=maps_dir,
    )

    for state in agent_map["states"].values():
        assert "delta_base_state" in state
        assert "delta_observed_items" in state

        for item in state.get("delta_observed_items", []):
            # delta_observed_items use the same short ref-preview format.
            assert "ref" in item
            assert item["ref"] in agent_map["items"]

            assert "role" in item
            assert "name" in item
            assert "description" in item

            assert "status" not in item
            assert "states" not in item
            assert "parent_path_tail" not in item
            assert "visible_bbox_hint" not in item
            assert "bbox" not in item


def test_top_level_items_hold_full_observed_item_details(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=FIXTURE,
    )

    store.save(graph)

    agent_map = build_agent_map(
        app="calc",
        maps_dir=maps_dir,
    )

    assert agent_map["items"]

    has_full_observed_item = False

    for item in agent_map["items"].values():
        assert item["status"] == "observed_unverified"
        assert "role" in item
        assert "name" in item
        assert "description" in item
        assert "states" in item
        assert "parent_path_tail" in item
        assert "bbox" not in item

        has_full_observed_item = True

    assert has_full_observed_item


def test_item_index_aggregates_observed_and_verified_items(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=FIXTURE,
    )

    edge = next(iter(graph.edges.values()))
    edge.status = EdgeStatus.SAME_STATE
    edge.to_state = edge.from_state
    edge.reason = "test same state edge"

    store.save(graph)

    agent_map = build_agent_map(
        app="calc",
        maps_dir=maps_dir,
    )

    index = agent_map["item_index"]

    assert index

    verified_entries = [
        item
        for item in index.values()
        if item["verified_action_count"] > 0
    ]

    observed_entries = [
        item
        for item in index.values()
        if item["observed_item_count"] > 0
    ]

    assert verified_entries
    assert observed_entries

    for item in verified_entries:
        assert "verified" in item["statuses"]

    for item in observed_entries:
        assert "observed_unverified" in item["statuses"]


def test_observed_item_refs_point_to_existing_items(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=FIXTURE,
    )

    store.save(graph)

    agent_map = build_agent_map(
        app="calc",
        maps_dir=maps_dir,
    )

    bad_refs = []

    for state_id, state in agent_map["states"].items():
        for section in ("observed_items", "delta_observed_items"):
            for item in state.get(section, []):
                ref = item.get("ref")
                if not ref or ref not in agent_map["items"]:
                    bad_refs.append((state_id, section, item))

    assert not bad_refs


def test_non_root_state_gets_incoming_action_and_delta_base(tmp_path):
    maps_dir = tmp_path / "maps"
    store = GraphStore(maps_dir)

    graph = store.init_from_xml(
        app_id="calc",
        xml_path=FIXTURE,
    )

    edge = next(iter(graph.edges.values()))
    edge.status = EdgeStatus.CONFIRMED
    edge.to_state = graph.root_state_id
    edge.reason = "test confirmed self-loop"

    store.save(graph)

    agent_map = build_agent_map(
        app="calc",
        maps_dir=maps_dir,
    )

    root_state = agent_map["states"][graph.root_state_id]

    # Root has no delta base, even if an incoming self-loop exists.
    assert root_state["delta_base_state"] is None
    assert root_state["delta_observed_items"] == []

    # Incoming actions are still recorded from verified edges.
    assert root_state["incoming_actions"]
    assert root_state["incoming_actions"][0]["from_state"] == graph.root_state_id
    assert root_state["incoming_actions"][0]["edge_status"] == "confirmed"
    assert root_state["incoming_actions"][0]["name"] == edge.action.get("name", "")
