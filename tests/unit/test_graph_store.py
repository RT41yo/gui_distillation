from pathlib import Path

from ui_explorer.graph.store import GraphStore


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def test_init_graph_from_xml(tmp_path):
    store = GraphStore(tmp_path / "maps")
    graph = store.init_from_xml(app_id="calc", xml_path=FIXTURE)

    assert graph.root_state_id
    assert len(graph.nodes) == 1
    assert len(graph.edges) > 0
    assert graph.completion["pending_edges"] == len(graph.edges)

    graph_path = store.graph_path("calc")
    assert graph_path.exists()


def test_graph_edges_are_keyed_by_state_and_action(tmp_path):
    store = GraphStore(tmp_path / "maps")
    graph = store.init_from_xml(app_id="calc", xml_path=FIXTURE)

    for edge_id, edge in graph.edges.items():
        assert edge_id == f"{edge.from_state}:{edge.action_key}"
        assert edge.status.value == "pending"
        assert edge.to_state is None
