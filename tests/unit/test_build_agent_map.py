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

    assert agent_map["schema_version"] == "1.0"
    assert agent_map["kind"] == "ui_explorer_agent_map"
    assert agent_map["app_id"] == "calc"
    assert agent_map["root_state_id"] == graph.root_state_id

    assert agent_map["summary"]["states"] == 1
    assert agent_map["summary"]["edges"] == len(graph.edges)
    assert agent_map["summary"]["pending_edges"] == len(graph.edges) - 1

    assert "usage_notes" in agent_map
    assert "states" in agent_map
    assert "item_index" in agent_map

    root_state = agent_map["states"][graph.root_state_id]

    assert root_state["state_id"] == graph.root_state_id
    assert root_state["depth"] == 0
    assert root_state["active_root"]["name"] == "Calculator"

    verified = root_state["verified_actions"]
    assert len(verified) == 1

    verified_action = verified[0]
    assert verified_action["status"] == "verified"
    assert verified_action["method"] == "bbox_click"
    assert verified_action["edge_status"] == "confirmed"
    assert verified_action["to_state"] == graph.root_state_id
    assert "bbox" in verified_action
    assert len(verified_action["bbox"]) == 4


def test_observed_items_do_not_expose_bbox(tmp_path):
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
            assert item["status"] == "observed_unverified"
            assert "bbox" not in item

    assert observed_total > 0


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
