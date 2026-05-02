from pathlib import Path

from ui_explorer.core.a11y_parser import parse_a11y_xml
from ui_explorer.graph.store import GraphStore


ROOT_XML = Path("data/maps/calc/_captures/a11y_tree.xml")
MENU_XML = Path("data/maps/calc/_tmp/step_edge/after.xml")


def test_seed_pending_edges_uses_active_root_for_menu_state(tmp_path):
    assert MENU_XML.exists(), "Run step_edge once to create menu-state XML fixture."

    store = GraphStore(tmp_path / "maps")
    graph = store.init_from_xml(app_id="calc", xml_path=ROOT_XML)

    root = parse_a11y_xml(MENU_XML)
    node = store.add_confirmed_state_from_xml(graph=graph, xml_path=MENU_XML, depth=1)

    outgoing = [
        edge for edge in graph.edges.values()
        if edge.from_state == node.state_id
    ]

    names = {edge.action["name"] for edge in outgoing}

    assert names == {"Binary", "Octal", "Decimal", "Hexadecimal"}
    assert len(outgoing) == 4
