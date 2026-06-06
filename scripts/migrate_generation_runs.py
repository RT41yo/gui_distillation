#!/usr/bin/env python3
"""Migrate synthetic workspace data to classification/ and task_generation/ layout."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from ui_explorer.synthetic.generation_output import (
    CLASSIFICATION_FILENAME,
    LEGACY_GENERATIONS_DIRNAME,
    METADATA_FILENAME,
    RUN_TIMESTAMP_PATTERN,
    classification_path,
    is_generation_run_dir,
    is_in_flight_generation_run_dir,
    is_legacy_flat_classification_state_dir,
    is_legacy_flat_generation_run,
    migrate_generation_run_layout,
    migrate_run_raw_layout,
    rewrite_generation_run_paths,
)
from ui_explorer.synthetic.paths import (
    CLASSIFICATION_DIRNAME,
    DEFAULT_CLASSIFICATION_MODEL,
    DEFAULT_OUTPUT_ROOT,
    TASK_GENERATION_DIRNAME,
    resolve_repo_path,
)


def is_legacy_task_model_dir(path: Path, *, workspace_root: Path) -> bool:
    if not path.is_dir() or path.parent != workspace_root:
        return False
    if path.name.startswith(".") or path.name in {CLASSIFICATION_DIRNAME, TASK_GENERATION_DIRNAME, "tasks"}:
        return False
    if is_legacy_flat_classification_state_dir(path, workspace_root=workspace_root):
        return False
    return any(child.is_dir() for child in path.iterdir())


def migrate_flat_classifications(
    workspace_root: Path,
    *,
    classification_model: str,
) -> list[dict[str, str]]:
    moves: list[dict[str, str]] = []
    for state_dir in sorted(workspace_root.iterdir()):
        if not is_legacy_flat_classification_state_dir(state_dir, workspace_root=workspace_root):
            continue
        source = state_dir / CLASSIFICATION_FILENAME
        target = classification_path(
            workspace_root,
            state_dir.name,
            classification_model=classification_model,
        )
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moves.append({"from": str(source), "to": str(target)})
        if not any(state_dir.iterdir()):
            state_dir.rmdir()
    return moves


def migrate_top_level_task_models(workspace_root: Path) -> list[dict[str, str]]:
    moves: list[dict[str, str]] = []
    tasks_root = workspace_root / TASK_GENERATION_DIRNAME
    tasks_root.mkdir(parents=True, exist_ok=True)

    for model_dir in sorted(workspace_root.iterdir()):
        if not is_legacy_task_model_dir(model_dir, workspace_root=workspace_root):
            continue
        target_model_dir = tasks_root / model_dir.name
        target_model_dir.mkdir(parents=True, exist_ok=True)
        for state_dir in sorted(model_dir.iterdir()):
            if not state_dir.is_dir():
                continue
            source = str(state_dir)
            target = target_model_dir / state_dir.name
            if target.exists():
                for run_dir in sorted(state_dir.iterdir()):
                    if not run_dir.is_dir():
                        continue
                    run_target = target / run_dir.name
                    if run_target.exists():
                        raise FileExistsError(f"cannot migrate {run_dir} because {run_target} exists")
                    run_dir.rename(run_target)
                    rewrite_generation_run_paths(run_target)
                    moves.append({"from": str(run_dir), "to": str(run_target)})
                if not any(state_dir.iterdir()):
                    state_dir.rmdir()
            else:
                state_dir.rename(target)
                moves.append({"from": source, "to": str(target)})
                for run_dir in target.iterdir():
                    if run_dir.is_dir() and RUN_TIMESTAMP_PATTERN.match(run_dir.name):
                        rewrite_generation_run_paths(run_dir)
        if not any(model_dir.iterdir()):
            model_dir.rmdir()
    return moves


def discover_legacy_generation_runs(workspace_root: Path) -> list[Path]:
    runs: list[Path] = []
    for state_dir in sorted(workspace_root.iterdir()):
        if not state_dir.is_dir():
            continue
        generations = state_dir / LEGACY_GENERATIONS_DIRNAME
        if not generations.exists():
            continue
        for child in sorted(generations.iterdir()):
            if not child.is_dir():
                continue
            if RUN_TIMESTAMP_PATTERN.match(child.name):
                if is_generation_run_dir(child) or is_in_flight_generation_run_dir(child):
                    runs.append(child)
                continue
            for run_dir in sorted(child.iterdir()):
                if run_dir.is_dir() and (
                    is_generation_run_dir(run_dir) or is_in_flight_generation_run_dir(run_dir)
                ):
                    runs.append(run_dir)
    return runs


def migrate_legacy_generation_runs(workspace_root: Path) -> list[dict[str, str]]:
    moves: list[dict[str, str]] = []
    for run_dir in discover_legacy_generation_runs(workspace_root):
        source = str(run_dir)
        target_path = migrate_generation_run_layout(
            run_dir,
            workspace_root=workspace_root,
        )
        if target_path is None:
            continue
        moves.append({"from": source, "to": str(target_path)})
    return moves


def remove_empty_legacy_generations_dirs(workspace_root: Path) -> list[str]:
    removed: list[str] = []
    for state_dir in sorted(workspace_root.iterdir()):
        if not state_dir.is_dir():
            continue
        generations = state_dir / LEGACY_GENERATIONS_DIRNAME
        if not generations.exists():
            continue
        for child in list(generations.iterdir()):
            if child.is_dir() and not any(child.iterdir()):
                child.rmdir()
        if not any(generations.iterdir()):
            removed.append(str(generations))
            generations.rmdir()
    return removed


def discover_generation_run_dirs(workspace_root: Path) -> list[Path]:
    runs: list[Path] = []
    tasks_root = workspace_root / TASK_GENERATION_DIRNAME
    if not tasks_root.exists():
        return runs
    for model_dir in sorted(tasks_root.iterdir()):
        if not model_dir.is_dir():
            continue
        for state_dir in sorted(model_dir.iterdir()):
            if not state_dir.is_dir():
                continue
            for run_dir in sorted(state_dir.iterdir()):
                if not run_dir.is_dir() or not RUN_TIMESTAMP_PATTERN.match(run_dir.name):
                    continue
                if is_generation_run_dir(run_dir) or is_in_flight_generation_run_dir(run_dir):
                    runs.append(run_dir)
    return runs


def migrate_flat_generation_runs(workspace_root: Path) -> list[dict[str, object]]:
    moves: list[dict[str, object]] = []
    for run_dir in discover_generation_run_dirs(workspace_root):
        if not is_legacy_flat_generation_run(run_dir):
            continue
        result = migrate_run_raw_layout(run_dir)
        if result is not None:
            moves.append(result)
    return moves


def rewrite_cost_log_paths(workspace_root: Path, moves: list[dict[str, str]]) -> int:
    path_map = {item["from"]: item["to"] for item in moves}
    if not path_map:
        return 0

    updated = 0
    for log_name in ("cost_task_generation.jsonl",):
        log_path = workspace_root / log_name
        if not log_path.exists():
            continue
        lines: list[str] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            generation_run = record.get("generation_run")
            if isinstance(generation_run, str):
                for old_path, new_path in path_map.items():
                    if generation_run == old_path or generation_run.startswith(old_path + "/"):
                        record["generation_run"] = generation_run.replace(old_path, new_path, 1)
                        updated += 1
                        break
            lines.append(json.dumps(record, ensure_ascii=False))
        log_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-root",
        "--classification-root",
        dest="workspace_root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--classification-model",
        default=DEFAULT_CLASSIFICATION_MODEL,
        help="Model directory name for migrated flat yield classifications.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace_root = resolve_repo_path(args.workspace_root)

    if args.dry_run:
        print(json.dumps({
            "dry_run": True,
            "flat_classifications": [
                str(path / CLASSIFICATION_FILENAME)
                for path in workspace_root.iterdir()
                if is_legacy_flat_classification_state_dir(path, workspace_root=workspace_root)
            ],
            "top_level_task_models": [
                str(path)
                for path in workspace_root.iterdir()
                if is_legacy_task_model_dir(path, workspace_root=workspace_root)
            ],
            "legacy_generation_runs": [str(path) for path in discover_legacy_generation_runs(workspace_root)],
            "flat_generation_runs": [
                str(path)
                for path in discover_generation_run_dirs(workspace_root)
                if is_legacy_flat_generation_run(path)
            ],
        }, indent=2))
        return 0

    classification_moves = migrate_flat_classifications(
        workspace_root,
        classification_model=args.classification_model,
    )
    task_moves = migrate_top_level_task_models(workspace_root)
    generation_moves = migrate_legacy_generation_runs(workspace_root)
    raw_layout_moves = migrate_flat_generation_runs(workspace_root)
    removed_empty = remove_empty_legacy_generations_dirs(workspace_root)
    moves = classification_moves + task_moves + generation_moves
    cost_updates = rewrite_cost_log_paths(workspace_root, moves)
    print(json.dumps({
        "ok": True,
        "classification_moves": classification_moves,
        "task_moves": task_moves,
        "generation_moves": generation_moves,
        "raw_layout_moves": raw_layout_moves,
        "removed_empty_generations_dirs": removed_empty,
        "cost_log_updates": cost_updates,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
