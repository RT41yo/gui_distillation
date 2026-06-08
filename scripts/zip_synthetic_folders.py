#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

CLASSIFICATION_ZIP = "classification.zip"
TASK_GENERATION_ZIP = "task_generation.zip"
FOLDERS = {
    "classification": CLASSIFICATION_ZIP,
    "task_generation": TASK_GENERATION_ZIP,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive classification/ and task_generation/ into zip files for Hub upload.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path("data/synthetic/libreoffice_writer/active_root_231"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Create zip files but keep the original loose folders",
    )
    return parser.parse_args()


def iter_folder_files(folder: Path) -> list[Path]:
    files = [path for path in folder.rglob("*") if path.is_file()]
    files.sort(key=lambda path: path.relative_to(folder).as_posix())
    return files


def zip_folder(folder: Path, zip_path: Path, *, dry_run: bool, remove_files: bool) -> dict:
    if not folder.is_dir():
        return {
            "folder": str(folder),
            "zip_path": str(zip_path),
            "skipped": True,
            "reason": "missing folder",
        }
    files = iter_folder_files(folder)
    if not files:
        return {
            "folder": str(folder),
            "zip_path": str(zip_path),
            "skipped": True,
            "reason": "no files",
        }
    if dry_run:
        return {
            "folder": str(folder),
            "zip_path": str(zip_path),
            "file_count": len(files),
            "total_bytes": sum(path.stat().st_size for path in files),
            "dry_run": True,
        }
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            archive.write(file_path, arcname=file_path.relative_to(folder).as_posix())
    removed = 0
    if remove_files:
        for file_path in files:
            file_path.unlink()
            removed += 1
        for path in sorted(folder.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            folder.rmdir()
        except OSError:
            pass
    return {
        "folder": str(folder),
        "zip_path": str(zip_path),
        "file_count": len(files),
        "removed_files": removed,
        "zip_bytes": zip_path.stat().st_size,
    }


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    summaries = [
        zip_folder(
            root / folder_name,
            root / zip_name,
            dry_run=args.dry_run,
            remove_files=not args.keep_files,
        )
        for folder_name, zip_name in FOLDERS.items()
    ]
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
