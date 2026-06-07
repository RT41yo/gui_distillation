#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import HfApi, upload_folder

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_ID = "tony-pitchblack/gui_distillation.data.synthetic"
DEFAULT_SOURCE = REPO_ROOT / "data/synthetic/libreoffice_writer"
DEFAULT_PATH_IN_REPO = "libreoffice_writer"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--path-in-repo", default=DEFAULT_PATH_IN_REPO)
    parser.add_argument("--commit-message", default="Add libreoffice_writer synthetic data")
    parser.add_argument("--exclude", action="append", default=["**/.logs/**"])
    parser.add_argument("--create", action="store_true", default=True)
    parser.add_argument("--no-create", dest="create", action="store_false")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"Missing source directory: {source}")

    api = HfApi()
    if args.create:
        api.create_repo(
            repo_id=args.repo_id,
            repo_type="dataset",
            exist_ok=True,
        )

    commit = upload_folder(
        repo_id=args.repo_id,
        repo_type="dataset",
        folder_path=str(source),
        path_in_repo=args.path_in_repo,
        commit_message=args.commit_message,
        ignore_patterns=args.exclude,
    )
    print(f"Uploaded {source} -> {args.repo_id}/{args.path_in_repo}")
    print(f"Commit: {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
