#!/usr/bin/env python3
"""Generate realistic Writer fixtures backed by downloaded OSWorld source documents."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

from ui_explorer.synthetic.paths import repo_root, resolve_repo_path
from ui_explorer.synthetic.writer_fixtures import (
    BLANK_FIXTURE,
    FIXTURE_FILENAMES,
    FIXTURE_SOURCE_RELATIVE_PATHS,
    resolve_writer_fixture_source_path,
    writer_fixtures_dir,
)


BLANK_DOCX_TEMPLATE_FILES = {
    "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
""",
    "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
""",
    "docProps/core.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Blank Writer Fixture</dc:title>
  <dc:creator>Cursor</dc:creator>
</cp:coreProperties>
""",
    "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Cursor</Application>
</Properties>
""",
    "word/document.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:w10="urn:schemas-microsoft-com:office:word" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" xmlns:wne="http://schemas.microsoft.com/office/2006/wordml" xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" mc:Ignorable="w14 wp14">
  <w:body>
    <w:p/>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
      <w:cols w:space="720"/>
      <w:docGrid w:linePitch="360"/>
    </w:sectPr>
  </w:body>
</w:document>
""",
}


def _write_blank_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in BLANK_DOCX_TEMPLATE_FILES.items():
            zf.writestr(name, content)


def generate_fixtures(output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    blank_path = output_dir / BLANK_FIXTURE
    _write_blank_docx(blank_path)
    created.append(str(blank_path))

    for fixture_name in FIXTURE_FILENAMES:
        if fixture_name == BLANK_FIXTURE:
            continue
        source_path = resolve_writer_fixture_source_path(fixture_name)
        if source_path is None or not source_path.exists():
            raise FileNotFoundError(f"missing OSWorld source for {fixture_name}: {source_path}")
        target_path = output_dir / fixture_name
        shutil.copy2(source_path, target_path)
        created.append(str(target_path))

    missing = sorted(set(FIXTURE_FILENAMES) - {Path(path).name for path in created})
    if missing:
        raise RuntimeError(f"fixture generation incomplete, missing: {missing}")
    return created


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root() / "data/source/fixtures/libreoffice_writer",
        help="Directory where Writer fixture files should be written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = resolve_repo_path(args.output_dir)
    created = generate_fixtures(output_dir)

    print(json.dumps({
        "ok": True,
        "output_dir": str(output_dir),
        "fixtures": created,
        "count": len(created),
        "sources": {
            name: (str(path) if path is not None else None)
            for name, path in (
                (fixture_name, resolve_writer_fixture_source_path(fixture_name))
                for fixture_name in FIXTURE_FILENAMES
            )
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
