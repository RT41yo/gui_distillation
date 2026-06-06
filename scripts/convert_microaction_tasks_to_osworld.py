#!/usr/bin/env python3
"""Convert raw microaction generation outputs into flat OSWorld task JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.synthetic.osworld_conversion import (
    convert_generation_run,
    discover_generation_runs,
    infer_snapshot_from_workspace,
)
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, resolve_repo_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-root",
        dest="workspace_root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Synthetic workspace root containing task_generation/ directories.",
    )
    parser.add_argument(
        "--generation-run",
        action="append",
        type=Path,
        default=[],
        help="Specific generation run container directory (repeatable).",
    )
    parser.add_argument(
        "--snapshot",
        default=None,
        help="Override snapshot/domain for converted tasks (default: inferred from workspace path).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing osworld/*.json files in target run directories.",
    )
    parser.add_argument(
        "--all-runs",
        action="store_true",
        help="Convert every discovered generation run under workspace-root.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace_root = resolve_repo_path(args.workspace_root)

    if args.generation_run:
        run_dirs = [resolve_repo_path(path) for path in args.generation_run]
    elif args.all_runs:
        run_dirs = discover_generation_runs(workspace_root)
    else:
        print(json.dumps({
            "ok": False,
            "error": "provide --generation-run and/or --all-runs",
        }, indent=2), file=sys.stderr)
        return 2

    if not run_dirs:
        print(json.dumps({
            "ok": False,
            "error": f"no generation runs found under {workspace_root}",
        }, indent=2), file=sys.stderr)
        return 1

    snapshot = args.snapshot
    if snapshot is None:
        try:
            snapshot = infer_snapshot_from_workspace(workspace_root)
        except ValueError:
            snapshot = None

    results: list[dict[str, object]] = []
    failed: list[dict[str, str]] = []
    for run_dir in run_dirs:
        try:
            results.append(convert_generation_run(
                run_dir,
                workspace_root=workspace_root,
                snapshot=snapshot,
                overwrite=args.overwrite,
            ))
        except Exception as exc:
            failed.append({"run_dir": str(run_dir), "error": str(exc)})

    print(json.dumps({
        "ok": not failed,
        "workspace_root": str(workspace_root),
        "snapshot": snapshot,
        "runs": results,
        "failed": failed,
        "converted_total": sum(int(item["converted_count"]) for item in results),
    }, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
