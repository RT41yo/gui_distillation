from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.paths import repo_root, resolve_repo_path

WRITER_FIXTURES_RELATIVE = Path("data/source/fixtures/libreoffice_writer")
VM_DESKTOP_DIR = "/home/user/Desktop"

FIXTURE_FILENAMES: tuple[str, ...] = (
    "blank.docx",
    "one_word.docx",
    "single_sentence.docx",
    "short_paragraph.docx",
    "two_paragraphs.docx",
    "bulleted_list.docx",
    "numbered_list.docx",
    "simple_table.docx",
    "table_with_values.docx",
    "styled_heading_and_body.docx",
)

LIST_TASK_TYPES = frozenset({"list_manipulation"})
TABLE_TASK_TYPES = frozenset({"table_structure", "table_content"})
STYLE_TASK_TYPES = frozenset({"paragraph_layout", "style_management", "selection_transform"})

BLANK_MARKERS = (
    "empty",
    "blank",
    "untitled",
    "fresh document",
    "new blank",
    "blank page",
    "startup",
    "idle editor",
    "ready for insertion",
    "ready for typing",
)


def writer_fixtures_dir(*, fixtures_root: Path | None = None) -> Path:
    root = resolve_repo_path(fixtures_root) if fixtures_root is not None else repo_root() / WRITER_FIXTURES_RELATIVE
    return root


def resolve_writer_fixture_path(fixture_name: str, *, fixtures_root: Path | None = None) -> Path:
    if fixture_name not in FIXTURE_FILENAMES:
        raise ValueError(f"unknown writer fixture: {fixture_name}")
    return writer_fixtures_dir(fixtures_root=fixtures_root) / fixture_name


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _precondition_text(preconditions: dict[str, Any] | None) -> str:
    if not isinstance(preconditions, dict):
        return ""
    parts = [_normalize_text(preconditions.get("description"))]
    extras = preconditions.get("extras")
    if isinstance(extras, list):
        for entry in extras:
            if not isinstance(entry, dict):
                continue
            parts.append(_normalize_text(entry.get("key")))
            parts.append(_normalize_text(entry.get("value")))
    return " ".join(part for part in parts if part)


def select_writer_fixture(
    *,
    task_type: str,
    preconditions: dict[str, Any] | None,
) -> str:
    combined = _precondition_text(preconditions)
    normalized_task_type = _normalize_text(task_type).replace(" ", "_")

    if normalized_task_type in TABLE_TASK_TYPES or "table" in combined:
        if normalized_task_type == "table_content" or any(
            marker in combined for marker in ("value", "values", "cell", "formula")
        ):
            return "table_with_values.docx"
        return "simple_table.docx"

    if normalized_task_type in LIST_TASK_TYPES or any(
        marker in combined for marker in ("bulleted", "numbered", "list item", "list")
    ):
        if "number" in combined:
            return "numbered_list.docx"
        return "bulleted_list.docx"

    if normalized_task_type in STYLE_TASK_TYPES or any(
        marker in combined for marker in ("heading", "style", "alignment", "center", "italic", "bold")
    ):
        if any(marker in combined for marker in BLANK_MARKERS):
            return "blank.docx"
        return "styled_heading_and_body.docx"

    if "one word" in combined:
        return "one_word.docx"
    if any(marker in combined for marker in ("sentence", "line of text", "short text", "line of text")):
        return "single_sentence.docx"
    if "two paragraph" in combined:
        return "two_paragraphs.docx"
    if any(marker in combined for marker in ("paragraph", "paragraph text")):
        if "blank paragraph" in combined or "empty paragraph" in combined:
            return "blank.docx"
        return "short_paragraph.docx"
    if any(marker in combined for marker in BLANK_MARKERS):
        return "blank.docx"
    return "blank.docx"


def vm_document_path(*, task_id: str) -> str:
    safe_id = task_id.replace("-", "")
    return f"{VM_DESKTOP_DIR}/synthetic_writer_{safe_id}.docx"


def vm_window_name(vm_document_path: str) -> str:
    basename = Path(vm_document_path).name
    return f"{basename} - LibreOffice Writer"


def build_writer_upload_open_config(
    *,
    fixture_name: str,
    task_id: str,
    fixtures_root: Path | None = None,
) -> list[dict[str, Any]]:
    local_fixture = resolve_writer_fixture_path(fixture_name, fixtures_root=fixtures_root).resolve()
    if not local_fixture.exists():
        raise FileNotFoundError(f"missing writer fixture: {local_fixture}")

    vm_path = vm_document_path(task_id=task_id)
    return [
        {
            "type": "upload_file",
            "parameters": {
                "files": [
                    {
                        "local_path": str(local_fixture),
                        "path": vm_path,
                    }
                ]
            },
        },
        {
            "type": "open",
            "parameters": {
                "path": vm_path,
            },
        },
    ]
