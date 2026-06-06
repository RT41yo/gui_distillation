#!/usr/bin/env python3
"""Migrate flat generations/{timestamp} runs to generations/{model}/{timestamp}."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.synthetic.generation_output import (
    GENERATIONS_DIRNAME,
    METADATA_FILENAME,
    migrate_legacy_generation_run,
)
from ui_explorer.synthetic.io import load_json
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, resolve_repo_path


def remove_incomplete_runs(classification_root: Path) -> list[str]:
    removed: list[str] = []
    for state_dir in sorted(classification_root.iterdir()):
        if not state_dir.is_dir():
            continue
        generations = state_dir / GENERATIONS_DIRNAME
        if not generations.exists():
            continue
        for child in generations.iterdir():
            if not child.is_dir():
                continue
            if (child / METADATA_FILENAME).exists():
                continue
            if any(child.iterdir()):
                removed.append(str(child))
                for path in sorted(child.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                child.rmdir()
    return removed


def migrate_runs(classification_root: Path) -> list[dict[str, str]]:
    moves: list[dict[str, str]] = []
    for state_dir in sorted(classification_root.iterdir()):
        if not state_dir.is_dir():
            continue
        generations = state_dir / GENERATIONS_DIRNAME
        if not generations.exists():
            continue
        for child in sorted(generations.iterdir()):
            if not child.is_dir():
                continue
            if child.parent.name != GENERATIONS_DIRNAME:
                continue
            if not (child / METADATA_FILENAME).exists():
                continue
            source = str(child)
            target_path = migrate_legacy_generation_run(child)
            if target_path is None:
                continue
            moves.append({"from": source, "to": str(target_path)})
    return moves


def rewrite_cost_log_paths(classification_root: Path, moves: list[dict[str, str]]) -> int:
    path_map = {item["from"]: item["to"] for item in moves}
    if not path_map:
        return 0

    updated = 0
    for log_name in ("cost_task_generation.jsonl",):
        log_path = classification_root / log_name
        if not log_path.exists():
            continue
        lines: list[str] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            generation_run = record.get("generation_run")
            if isinstance(generation_run, str) and generation_run in path_map:
                record["generation_run"] = path_map[generation_run]
                updated += 1
            lines.append(json.dumps(record, ensure_ascii=False))
        log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classification-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    classification_root = resolve_repo_path(args.classification_root)

    if args.dry_run:
        candidates = []
        for state_dir in sorted(classification_root.iterdir()):
            generations = state_dir / GENERATIONS_DIRNAME
            if not generations.exists():
                continue
            for child in generations.iterdir():
                if child.is_dir() and (child / METADATA_FILENAME).exists() and child.parent.name == GENERATIONS_DIRNAME:
                    candidates.append(str(child))
        print(json.dumps({"dry_run": True, "candidates": candidates}, indent=2))
        return 0

    removed = remove_incomplete_runs(classification_root)
    moves = migrate_runs(classification_root)
    cost_updates = rewrite_cost_log_paths(classification_root, moves)
    print(json.dumps({
        "ok": True,
        "removed_incomplete": removed,
        "moved": moves,
        "cost_log_updates": cost_updates,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
