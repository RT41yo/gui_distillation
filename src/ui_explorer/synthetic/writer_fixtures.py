from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.paths import repo_root, resolve_repo_path

WRITER_FIXTURES_RELATIVE = Path("data/source/fixtures/libreoffice_writer")
WRITER_OSWORLD_SOURCE_RELATIVE = Path("data/source/osworld/libreoffice_writer")
VM_DESKTOP_DIR = "/home/user/Desktop"

BLANK_FIXTURE = "blank__generated_empty.docx"
ONE_WORD_FIXTURE = "one_word__h2o_factsheet_wa.docx"
SINGLE_SENTENCE_FIXTURE = "single_sentence__04_chin9505_ebook_purchasing_info_2021_jan.docx"
SHORT_PARAGRAPH_FIXTURE = "short_paragraph__dublin_zoo_intro.docx"
TWO_PARAGRAPHS_FIXTURE = "two_paragraphs__novels_intro_packet.docx"
BULLETED_LIST_FIXTURE = "bulleted_list__ccch9003_tutorial_guidelines.docx"
NUMBERED_LIST_FIXTURE = "numbered_list__constitution_template_with_guidelines.docx"
SIMPLE_TABLE_FIXTURE = "simple_table__table_of_work_effort_instructions.docx"
TABLE_WITH_VALUES_FIXTURE = "table_with_values__view_person_organizational_summary.docx"
STYLED_HEADING_AND_BODY_FIXTURE = "styled_heading_and_body__constitution_template_with_guidelines.docx"
HIGHLIGHTED_TEXT_FIXTURE = "highlighted_text__sample_recruitment_phone_script.odt"
IMAGE_ANCHOR_FIXTURE = "image_anchor__viewing_your_class_schedule_and_textbooks.docx"
CROSS_REFERENCE_FIXTURE = "cross_reference__essay_writing_english_for_uni.docx"

FIXTURE_SOURCE_RELATIVE_PATHS: dict[str, Path | None] = {
    BLANK_FIXTURE: None,
    ONE_WORD_FIXTURE: Path("0b17a146-2934-46c7-8727-73ff6b6483e8/H2O_Factsheet_WA.docx"),
    SINGLE_SENTENCE_FIXTURE: Path("0a0faba3-5580-44df-965d-f562a99b291c/04 CHIN9505 EBook Purchasing info 2021 Jan.docx"),
    SHORT_PARAGRAPH_FIXTURE: Path("0e763496-b6bb-4508-a427-fad0b6c3e195/Dublin_Zoo_Intro.docx"),
    TWO_PARAGRAPHS_FIXTURE: Path("0810415c-bde4-4443-9047-d5f70165a697/Novels_Intro_Packet.docx"),
    BULLETED_LIST_FIXTURE: Path("88fe4b2d-3040-4c70-9a70-546a47764b48/CCCH9003_Tutorial_guidelines.docx"),
    NUMBERED_LIST_FIXTURE: Path("3ef2b351-8a84-4ff2-8724-d86eae9b842e/Constitution_Template_With_Guidelines.docx"),
    SIMPLE_TABLE_FIXTURE: Path("66399b0d-8fda-4618-95c4-bfc6191617e9/Table_Of_Work_Effort_Instructions.docx"),
    TABLE_WITH_VALUES_FIXTURE: Path("4bcb1253-a636-4df4-8cb0-a35c04dfef31/View_Person_Organizational_Summary.docx"),
    STYLED_HEADING_AND_BODY_FIXTURE: Path("3ef2b351-8a84-4ff2-8724-d86eae9b842e/Constitution_Template_With_Guidelines.docx"),
    HIGHLIGHTED_TEXT_FIXTURE: Path("6a33f9b9-0a56-4844-9c3f-96ec3ffb3ba2/sample-recruitment-phone-script.odt"),
    IMAGE_ANCHOR_FIXTURE: Path("6ada715d-3aae-4a32-a6a7-429b2e43fb93/Viewing_Your_Class_Schedule_and_Textbooks.docx"),
    CROSS_REFERENCE_FIXTURE: Path("adf5e2c3-64c7-4644-b7b6-d2f0167927e7/Essay_Writing_English_for_uni.docx"),
}

FIXTURE_FILENAMES: tuple[str, ...] = tuple(FIXTURE_SOURCE_RELATIVE_PATHS)

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


def writer_osworld_sources_dir(*, sources_root: Path | None = None) -> Path:
    root = resolve_repo_path(sources_root) if sources_root is not None else repo_root() / WRITER_OSWORLD_SOURCE_RELATIVE
    return root


def resolve_writer_fixture_path(fixture_name: str, *, fixtures_root: Path | None = None) -> Path:
    if fixture_name not in FIXTURE_FILENAMES:
        raise ValueError(f"unknown writer fixture: {fixture_name}")
    return writer_fixtures_dir(fixtures_root=fixtures_root) / fixture_name


def resolve_writer_fixture_source_path(
    fixture_name: str,
    *,
    sources_root: Path | None = None,
) -> Path | None:
    if fixture_name not in FIXTURE_SOURCE_RELATIVE_PATHS:
        raise ValueError(f"unknown writer fixture: {fixture_name}")
    relative = FIXTURE_SOURCE_RELATIVE_PATHS[fixture_name]
    if relative is None:
        return None
    return writer_osworld_sources_dir(sources_root=sources_root) / relative


def fixture_file_suffix(fixture_name: str) -> str:
    return Path(fixture_name).suffix or ".docx"


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

    if any(marker in combined for marker in ("highlight", "highlighted", "yellow mark")):
        return HIGHLIGHTED_TEXT_FIXTURE
    if any(marker in combined for marker in ("image", "photo", "picture", "screenshot", "png")):
        return IMAGE_ANCHOR_FIXTURE
    if any(marker in combined for marker in ("cross reference", "reference list", "bibliography", "citation")):
        return CROSS_REFERENCE_FIXTURE

    if normalized_task_type in TABLE_TASK_TYPES or "table" in combined:
        if normalized_task_type == "table_content" or any(
            marker in combined for marker in ("value", "values", "cell", "formula")
        ):
            return TABLE_WITH_VALUES_FIXTURE
        return SIMPLE_TABLE_FIXTURE

    if normalized_task_type in LIST_TASK_TYPES or any(
        marker in combined for marker in ("bulleted", "numbered", "list item", "list")
    ):
        if "number" in combined:
            return NUMBERED_LIST_FIXTURE
        return BULLETED_LIST_FIXTURE

    if normalized_task_type in STYLE_TASK_TYPES or any(
        marker in combined for marker in ("heading", "style", "alignment", "center", "italic", "bold")
    ):
        if any(marker in combined for marker in BLANK_MARKERS):
            return BLANK_FIXTURE
        return STYLED_HEADING_AND_BODY_FIXTURE

    if "one word" in combined:
        return ONE_WORD_FIXTURE
    if any(marker in combined for marker in ("sentence", "line of text", "short text", "line of text")):
        return SINGLE_SENTENCE_FIXTURE
    if "two paragraph" in combined:
        return TWO_PARAGRAPHS_FIXTURE
    if any(marker in combined for marker in ("paragraph", "paragraph text")):
        if "blank paragraph" in combined or "empty paragraph" in combined:
            return BLANK_FIXTURE
        return SHORT_PARAGRAPH_FIXTURE
    if any(marker in combined for marker in BLANK_MARKERS):
        return BLANK_FIXTURE
    return BLANK_FIXTURE


def vm_document_path(*, task_id: str, suffix: str = ".docx") -> str:
    safe_id = task_id.replace("-", "")
    resolved_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{VM_DESKTOP_DIR}/synthetic_writer_{safe_id}{resolved_suffix}"


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

    vm_path = vm_document_path(task_id=task_id, suffix=local_fixture.suffix)
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
