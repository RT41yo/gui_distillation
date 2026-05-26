from pathlib import Path

from ui_explorer.core.a11y_parser import parse_a11y_xml
from ui_explorer.core.state import compute_state_signature


FIXTURE = Path("data/maps/calc/_captures/a11y_tree.xml")


def test_state_signature_is_stable_for_same_xml():
    root1 = parse_a11y_xml(FIXTURE)
    root2 = parse_a11y_xml(FIXTURE)

    sig1 = compute_state_signature(root1)
    sig2 = compute_state_signature(root2)

    assert sig1.state_id == sig2.state_id
    assert sig1.macro_hash == sig2.macro_hash
    assert sig1.content_hash == sig2.content_hash


def test_state_signature_is_a11y_only():
    root = parse_a11y_xml(FIXTURE)
    sig = compute_state_signature(root)

    data = sig.to_dict()

    assert data["signature_source"] == "a11y_only"
    assert data["screenshot_used"] is False


def test_state_signature_has_macro_actions():
    root = parse_a11y_xml(FIXTURE)
    sig = compute_state_signature(root)

    assert sig.state_id
    assert len(sig.state_id) == 12
    assert sig.macro_action_count > 0
    assert sig.active_root["role"] == "frame"


def test_libreoffice_writer_state_signature_uses_main_frame():
    path = Path("tests/fixtures/a11y/writer/root_pos_a.xml")
    assert path.exists(), "Run Writer capture first."

    root = parse_a11y_xml(path)
    sig = compute_state_signature(root)

    assert sig.active_root["kind"] == "main"
    assert sig.active_root["role"] == "frame"
    assert sig.macro_action_count > 0
    assert sig.visible_node_count > 1


def test_writer_state_signature_ignores_window_position_shift():
    p1 = Path("tests/fixtures/a11y/writer/root_pos_a.xml")
    p2 = Path("tests/fixtures/a11y/writer/root_pos_b.xml")

    assert p1.exists()
    assert p2.exists()

    sig1 = compute_state_signature(parse_a11y_xml(p1))
    sig2 = compute_state_signature(parse_a11y_xml(p2))

    assert sig1.active_root["role"] == "frame"
    assert sig2.active_root["role"] == "frame"
    assert sig1.active_root["name"] == "Untitled 1 - LibreOffice Writer"
    assert sig2.active_root["name"] == "Untitled 1 - LibreOffice Writer"

    assert sig1.macro_action_count == sig2.macro_action_count
    assert sig1.macro_action_count > 0

    assert sig1.state_id == sig2.state_id
    assert sig1.macro_hash == sig2.macro_hash

    # Content can differ while macro/navigation state remains the same.
    assert sig1.content_hash != sig2.content_hash

