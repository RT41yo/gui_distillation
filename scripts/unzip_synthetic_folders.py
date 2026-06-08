#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

CLASSIFICATION_ZIP = "classification.zip"
TASK_GENERATION_ZIP = "task_generation.zip"
ARCHIVES = {
    CLASSIFICATION_ZIP: "classification",
    TASK_GENERATION_ZIP: "task_generation",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore classification/ and task_generation/ from zip files after Hub download.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path("data/synthetic/libreoffice_writer/active_root_231"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--remove-zip", action="store_true")
    return parser.parse_args()


def unzip_archive(zip_path: Path, folder: Path, *, dry_run: bool, remove_zip: bool) -> dict:
    if not zip_path.is_file():
        return {
            "zip_path": str(zip_path),
            "folder": str(folder),
            "skipped": True,
            "reason": "missing zip",
        }
    if dry_run:
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
        return {
            "zip_path": str(zip_path),
            "folder": str(folder),
            "file_count": len(members),
            "dry_run": True,
        }
    folder.mkdir(parents=True, exist_ok=True)
    extracted = 0
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.namelist():
            if member.endswith("/"):
                continue
            target = folder / member
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as handle:
                handle.write(source.read())
            extracted += 1
    if remove_zip:
        zip_path.unlink()
    return {
        "zip_path": str(zip_path),
        "folder": str(folder),
        "extracted_files": extracted,
        "removed_zip": remove_zip,
    }


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    summaries = [
        unzip_archive(
            root / zip_name,
            root / folder_name,
            dry_run=args.dry_run,
            remove_zip=args.remove_zip,
        )
        for zip_name, folder_name in ARCHIVES.items()
    ]
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
