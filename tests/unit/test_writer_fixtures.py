from __future__ import annotations

from pathlib import Path

from ui_explorer.synthetic.writer_fixtures import (
    build_writer_upload_open_config,
    resolve_writer_fixture_path,
    select_writer_fixture,
    vm_document_path,
    writer_fixtures_dir,
)


def test_writer_fixtures_exist_in_repo() -> None:
    fixtures_dir = writer_fixtures_dir()
    assert fixtures_dir.is_dir()
    assert resolve_writer_fixture_path("blank.docx").exists()


def test_select_writer_fixture_maps_blank_document() -> None:
    fixture = select_writer_fixture(
        task_type="cursor_format_toggle",
        preconditions={
            "description": "Blank Writer document with the text cursor active in the body area.",
            "extras": [
                {"key": "document_state", "value": "empty"},
                {"key": "selection", "value": "none"},
            ],
        },
    )
    assert fixture == "blank.docx"


def test_select_writer_fixture_maps_table_tasks() -> None:
    fixture = select_writer_fixture(
        task_type="table_content",
        preconditions={
            "description": "Document contains a table with concrete values.",
            "extras": [{"key": "document_state", "value": "table present"}],
        },
    )
    assert fixture == "table_with_values.docx"


def test_build_writer_upload_open_config_shape() -> None:
    task_id = "01e96009-9b36-5304-a0c1-eecd17be251e"
    config = build_writer_upload_open_config(fixture_name="blank.docx", task_id=task_id)
    assert len(config) == 2
    assert config[0]["type"] == "upload_file"
    assert config[1]["type"] == "open"
    local_path = config[0]["parameters"]["files"][0]["local_path"]
    vm_path = config[0]["parameters"]["files"][0]["path"]
    assert Path(local_path).exists()
    assert vm_path == vm_document_path(task_id=task_id)
    assert config[1]["parameters"]["path"] == vm_path
