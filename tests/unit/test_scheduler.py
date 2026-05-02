from pathlib import Path

from ui_explorer.graph.scheduler import BFSScheduler
from ui_explorer.graph.store import GraphStore


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def test_scheduler_returns_pending_edge(tmp_path):
    store = GraphStore(tmp_path / "maps")
    graph = store.init_from_xml(app_id="calc", xml_path=FIXTURE)

    edge = BFSScheduler().next_edge(graph)

    assert edge is not None
    assert edge.status.value == "pending"


def test_scheduler_prefers_lowest_priority_within_depth(tmp_path):
    store = GraphStore(tmp_path / "maps")
    graph = store.init_from_xml(app_id="calc", xml_path=FIXTURE)

    edge = BFSScheduler().next_edge(graph)

    assert edge is not None
    assert edge.priority == min(e.priority for e in graph.edges.values())
