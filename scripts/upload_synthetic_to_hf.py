#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import HfApi, upload_folder

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_ID = "tony-pitchblack/gui_distillation.data.synthetic"
DEFAULT_SOURCE = REPO_ROOT / "data/synthetic/libreoffice_writer"
DEFAULT_PATH_IN_REPO = "libreoffice_writer"
CLASSIFICATION_ZIP = "classification.zip"
TASK_GENERATION_ZIP = "task_generation.zip"
DEFAULT_IGNORE = [
    "**/.logs/**",
    "**/active_root_*/classification/**",
    "**/active_root_*/task_generation/**",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--path-in-repo", default=DEFAULT_PATH_IN_REPO)
    parser.add_argument(
        "--commit-message",
        default="Repack libreoffice_writer synthetic data as zip archives",
    )
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--create", action="store_true", default=True)
    parser.add_argument("--no-create", dest="create", action="store_false")
    parser.add_argument(
        "--replace-loose",
        action="store_true",
        help="Delete loose classification/ and task_generation/ trees on the Hub before upload",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def active_roots(source: Path) -> list[Path]:
    return sorted(path for path in source.glob("active_root_*") if path.is_dir())


def validate_archives(source: Path) -> None:
    missing: list[str] = []
    for root in active_roots(source):
        for name in (CLASSIFICATION_ZIP, TASK_GENERATION_ZIP):
            if not (root / name).is_file():
                missing.append(f"{root.name}/{name}")
    if missing:
        raise SystemExit(
            "Missing zip archives (run scripts/zip_synthetic_folders.py first):\n  "
            + "\n  ".join(missing)
        )


def delete_loose_hub_trees(api: HfApi, repo_id: str, path_in_repo: str, source: Path) -> list[str]:
    deleted: list[str] = []
    prefix = path_in_repo.strip("/")
    for root in active_roots(source):
        for folder in ("classification", "task_generation"):
            hub_path = f"{prefix}/{root.name}/{folder}"
            api.delete_folder(
                path_in_repo=hub_path,
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=f"Remove loose {folder} tree before zip upload",
            )
            deleted.append(hub_path)
    return deleted


def main() -> int:
    args = parse_args()
    source = args.source.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"Missing source directory: {source}")

    validate_archives(source)
    ignore_patterns = DEFAULT_IGNORE + list(args.exclude)

    if args.dry_run:
        uploads = [path.relative_to(source).as_posix() for path in sorted(source.rglob("*")) if path.is_file()]
        filtered = []
        from fnmatch import fnmatch

        for item in uploads:
            if any(fnmatch(item, pattern) for pattern in ignore_patterns):
                continue
            filtered.append(item)
        print(f"Would upload {len(filtered)} files to {args.repo_id}/{args.path_in_repo}")
        for item in filtered:
            print(f"  {item}")
        if args.replace_loose:
            for root in active_roots(source):
                for folder in ("classification", "task_generation"):
                    print(f"Would delete {args.path_in_repo}/{root.name}/{folder}")
        return 0

    api = HfApi()
    if args.create:
        api.create_repo(
            repo_id=args.repo_id,
            repo_type="dataset",
            exist_ok=True,
        )

    if args.replace_loose:
        deleted = delete_loose_hub_trees(api, args.repo_id, args.path_in_repo, source)
        for path in deleted:
            print(f"Deleted {path}")

    commit = upload_folder(
        repo_id=args.repo_id,
        repo_type="dataset",
        folder_path=str(source),
        path_in_repo=args.path_in_repo,
        commit_message=args.commit_message,
        ignore_patterns=ignore_patterns,
    )
    print(f"Uploaded {source} -> {args.repo_id}/{args.path_in_repo}")
    print(f"Commit: {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
