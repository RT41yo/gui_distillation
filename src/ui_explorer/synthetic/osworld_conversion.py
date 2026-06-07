from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.generation_output import (
    METADATA_FILENAME,
    MICROACTION_OUTPUT_PATTERN,
    RAW_RESPONSE_BATCH_PATTERN,
    SETTINGS_FILENAME,
    metadata_path,
    osworld_generation_dir,
    raw_generation_dir,
)
from ui_explorer.synthetic.io import load_json, save_json
from ui_explorer.synthetic.scope_index import ScopeIndex
from ui_explorer.synthetic.writer_fixtures import (
    build_writer_upload_open_config,
    fixture_file_suffix,
    select_writer_fixture,
    vm_document_path,
    vm_window_name,
)
from ui_explorer.synthetic.writer_macrostate_setup import build_writer_macrostate_preflight

OSWORLD_DUMMY_EVALUATOR_FUNC = "always_dummy"
LIBREOFFICE_WRITER_SNAPSHOT = "libreoffice_writer"
SYNTHETIC_TASK_NAMESPACE = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")


def infer_snapshot_from_workspace(workspace_root: Path) -> str:
    parts = workspace_root.parts
    if "synthetic" in parts:
        index = parts.index("synthetic")
        if index + 1 < len(parts):
            return parts[index + 1]
    raise ValueError(f"cannot infer snapshot/domain from workspace root: {workspace_root}")


def deterministic_task_id(*, run_timestamp: str, micro_action_id: str, task_index: int) -> str:
    seed = f"{run_timestamp}/{micro_action_id}/{task_index}"
    return str(uuid.uuid5(SYNTHETIC_TASK_NAMESPACE, seed))


def list_raw_microaction_files(run_dir: Path) -> list[Path]:
    raw_dir = raw_generation_dir(run_dir)
    if not raw_dir.exists():
        return []
    return sorted(
        child
        for child in raw_dir.iterdir()
        if child.is_file()
        and MICROACTION_OUTPUT_PATTERN.match(child.name)
        and child.name not in {SETTINGS_FILENAME, METADATA_FILENAME}
    )


def _load_scope_index(workspace_root: Path) -> ScopeIndex | None:
    from ui_explorer.synthetic.paths import repo_root

    candidates = [repo_root(), workspace_root]
    while workspace_root.parent != workspace_root:
        candidates.append(workspace_root)
        workspace_root = workspace_root.parent

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        scope_path = resolved / "data/maps/libreoffice_writer/agent_map_active_root_scope.json"
        agent_path = resolved / "data/maps/libreoffice_writer/agent_map.json"
        if scope_path.exists() and agent_path.exists():
            try:
                return ScopeIndex.load(repo_root=resolved)
            except Exception:
                continue
    return None


def build_osworld_task(
    *,
    run_dir: Path,
    workspace_root: Path,
    microaction_payload: dict[str, Any],
    task_entry: dict[str, Any],
    task_index: int,
    snapshot: str | None = None,
    scope_index: ScopeIndex | None = None,
) -> dict[str, Any]:
    micro_action_id = str(microaction_payload["micro_action_id"])
    task_type = str(microaction_payload.get("task_type", "unknown"))
    run_timestamp = run_dir.name
    task_id = deterministic_task_id(
        run_timestamp=run_timestamp,
        micro_action_id=micro_action_id,
        task_index=task_index,
    )
    resolved_snapshot = snapshot or infer_snapshot_from_workspace(workspace_root)

    metadata_file = metadata_path(run_dir)
    macro_state_id = None
    if metadata_file.exists():
        metadata = load_json(metadata_file)
        macro_state_id = metadata.get("macro_state_id")

    preconditions = task_entry.get("preconditions")
    if not isinstance(preconditions, dict):
        preconditions = {}

    synthetic_metadata = {
        "source": "gui_distillation.microaction_tasks",
        "generation_run": str(run_dir),
        "macro_state_id": macro_state_id,
        "micro_action_id": micro_action_id,
        "task_type": task_type,
        "task_index": task_index,
        "expected_outcome": task_entry.get("expected_outcome"),
        "preconditions": preconditions,
    }

    if resolved_snapshot == LIBREOFFICE_WRITER_SNAPSHOT:
        fixture_name = select_writer_fixture(task_type=task_type, preconditions=preconditions)
        config = build_writer_upload_open_config(fixture_name=fixture_name, task_id=task_id)
        vm_path = vm_document_path(task_id=task_id, suffix=fixture_file_suffix(fixture_name))
        window_name = vm_window_name(vm_path)
        synthetic_metadata.update({
            "fixture": fixture_name,
            "vm_document_path": vm_path,
            "window_name": window_name,
        })

        macrostate_setup: dict[str, Any] = {"status": "skipped", "reason": "no macro_state_id"}
        if isinstance(macro_state_id, str) and macro_state_id.strip():
            resolved_scope = scope_index or _load_scope_index(workspace_root)
            if resolved_scope is None:
                macrostate_setup = {
                    "status": "unsupported",
                    "reason": "scope maps unavailable",
                    "macro_state_id": macro_state_id,
                }
            else:
                preflight_block, macrostate_setup = build_writer_macrostate_preflight(
                    resolved_scope,
                    macro_state_id=macro_state_id.strip(),
                    vm_document_path=vm_path,
                )
                if preflight_block is not None:
                    config.append({
                        "type": "activate_window",
                        "parameters": {
                            "window_name": window_name,
                            "strict": False,
                        },
                    })
                    config.append(preflight_block)
        synthetic_metadata["macrostate_setup"] = macrostate_setup

        return {
            "id": task_id,
            "snapshot": resolved_snapshot,
            "instruction": str(task_entry["instruction"]).strip(),
            "source": "gui_distillation.microaction_tasks",
            "config": config,
            "trajectory": "trajectories/",
            "related_apps": [resolved_snapshot],
            "evaluator": {
                "func": OSWORLD_DUMMY_EVALUATOR_FUNC,
            },
            "synthetic": synthetic_metadata,
        }

    return {
        "id": task_id,
        "task_id": task_id,
        "snapshot": resolved_snapshot,
        "instruction": str(task_entry["instruction"]).strip(),
        "config": [],
        "related_apps": [resolved_snapshot],
        "os": "ubuntu",
        "evaluator": {
            "func": OSWORLD_DUMMY_EVALUATOR_FUNC,
        },
        "synthetic": synthetic_metadata,
    }


def convert_generation_run(
    run_dir: Path,
    *,
    workspace_root: Path,
    snapshot: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    if not run_dir.is_dir():
        raise FileNotFoundError(f"generation run not found: {run_dir}")

    output_dir = osworld_generation_dir(run_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"osworld output already exists under {output_dir}; pass overwrite=True to replace"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for child in output_dir.iterdir():
            if child.is_file() and child.suffix == ".json":
                child.unlink()

    scope_index = _load_scope_index(workspace_root)

    converted: list[dict[str, str]] = []
    skipped = 0
    for microaction_file in list_raw_microaction_files(run_dir):
        payload = load_json(microaction_file)
        tasks = payload.get("task")
        if not isinstance(tasks, list):
            skipped += 1
            continue
        for task_index, task_entry in enumerate(tasks):
            if not isinstance(task_entry, dict):
                skipped += 1
                continue
            osworld_task = build_osworld_task(
                run_dir=run_dir,
                workspace_root=workspace_root,
                microaction_payload=payload,
                task_entry=task_entry,
                task_index=task_index,
                snapshot=snapshot,
                scope_index=scope_index,
            )
            output_path = output_dir / f"{osworld_task['id']}.json"
            save_json(output_path, osworld_task)
            converted.append({
                "task_id": osworld_task["id"],
                "path": str(output_path),
                "micro_action_id": str(payload.get("micro_action_id")),
                "task_index": str(task_index),
            })

    return {
        "run_dir": str(run_dir),
        "osworld_dir": str(output_dir),
        "converted_count": len(converted),
        "skipped_count": skipped,
        "converted": converted,
    }


def discover_generation_runs(workspace_root: Path) -> list[Path]:
    from ui_explorer.synthetic.generation_output import list_generation_runs
    from ui_explorer.synthetic.paths import TASK_GENERATION_DIRNAME

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
            runs.extend(list_generation_runs(workspace_root, state_dir.name, model=model_dir.name))
    return sorted(runs, key=lambda path: path.name)


def is_raw_microaction_file(path: Path) -> bool:
    return (
        path.is_file()
        and MICROACTION_OUTPUT_PATTERN.match(path.name) is not None
        and not RAW_RESPONSE_BATCH_PATTERN.match(path.name)
    )
