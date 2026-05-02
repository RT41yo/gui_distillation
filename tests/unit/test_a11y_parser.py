from pathlib import Path

from ui_explorer.core.a11y_parser import parse_a11y_xml, visible_nodes, walk


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def test_parse_captured_xml_has_nodes():
    assert FIXTURE.exists(), "Run capture CLI first to create the A11Y XML fixture."

    root = parse_a11y_xml(FIXTURE)
    nodes = list(walk(root))

    assert root.role == "application"
    assert len(nodes) > 0


def test_parse_captured_xml_has_visible_nodes():
    root = parse_a11y_xml(FIXTURE)
    nodes = visible_nodes(root)

    assert len(nodes) > 0
    assert all(node.bbox.width > 1 for node in nodes)
    assert all(node.bbox.height > 1 for node in nodes)
    assert all(node.bbox.x >= 0 for node in nodes)
    assert all(node.bbox.y >= 0 for node in nodes)
