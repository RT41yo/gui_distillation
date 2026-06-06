from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.io import load_json, save_json
from ui_explorer.synthetic.paths import CLASSIFICATION_DIRNAME, TASK_GENERATION_DIRNAME
from ui_explorer.synthetic.schemas import YIELD_BUCKETS

LEGACY_GENERATIONS_DIRNAME = "generations"
SETTINGS_FILENAME = "settings.json"
METADATA_FILENAME = "metadata.json"
CLASSIFICATION_FILENAME = "yield_classification.json"
RAW_RESPONSE_BATCH_PATTERN = re.compile(r"^raw_response_batch_(\d+)\.json$")
RUN_TIMESTAMP_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")

GENERATION_STATUS_IN_PROGRESS = "in_progress"
GENERATION_STATUS_GENERATED = "generated"
GENERATION_STATUS_PARTIAL = "partial"
GENERATION_STATUS_FAILED = "failed"
FINAL_GENERATION_STATUSES = frozenset({
    GENERATION_STATUS_GENERATED,
    GENERATION_STATUS_PARTIAL,
    GENERATION_STATUS_FAILED,
    "dry_run",
})


def utc_run_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def model_dir_name(model: str) -> str:
    slug = (model or "unknown").strip() or "unknown"
    return slug.replace("/", "_").replace("\\", "_")


def classification_model_dir(workspace_root: Path, *, classification_model: str) -> Path:
    return workspace_root / CLASSIFICATION_DIRNAME / model_dir_name(classification_model)


def classification_path(
    workspace_root: Path,
    state_id: str,
    *,
    classification_model: str,
) -> Path:
    return classification_model_dir(workspace_root, classification_model=classification_model) / state_id / CLASSIFICATION_FILENAME


def tasks_model_dir(workspace_root: Path, *, model: str) -> Path:
    return workspace_root / TASK_GENERATION_DIRNAME / model_dir_name(model)


def macro_state_tasks_dir(
    workspace_root: Path,
    state_id: str,
    *,
    model: str,
) -> Path:
    return tasks_model_dir(workspace_root, model=model) / state_id


def generation_run_dir(
    workspace_root: Path,
    state_id: str,
    *,
    model: str,
    timestamp: str | None = None,
) -> Path:
    run_id = timestamp or utc_run_timestamp()
    return macro_state_tasks_dir(workspace_root, state_id, model=model) / run_id


def is_classification_macro_state_dir(path: Path) -> bool:
    return path.is_dir() and (path / CLASSIFICATION_FILENAME).exists()


def is_legacy_flat_classification_state_dir(path: Path, *, workspace_root: Path) -> bool:
    return path.parent == workspace_root and is_classification_macro_state_dir(path)


def list_classification_models(workspace_root: Path) -> list[str]:
    classification_root = workspace_root / CLASSIFICATION_DIRNAME
    if not classification_root.exists():
        return []
    return sorted(
        child.name
        for child in classification_root.iterdir()
        if child.is_dir()
    )


def resolve_classification_model(
    workspace_root: Path,
    override: str | None = None,
) -> str:
    if override:
        return model_dir_name(override)
    models = list_classification_models(workspace_root)
    if len(models) == 1:
        return models[0]
    if not models:
        raise FileNotFoundError(
            f"no classification model directories under {workspace_root / CLASSIFICATION_DIRNAME}"
        )
    raise ValueError(
        "multiple classification models found "
        f"({', '.join(models)}); pass --classification-model"
    )


def list_classified_state_ids(
    workspace_root: Path,
    *,
    classification_model: str,
) -> list[str]:
    model_dir = classification_model_dir(workspace_root, classification_model=classification_model)
    if not model_dir.exists():
        return []
    return sorted(
        child.name
        for child in model_dir.iterdir()
        if is_classification_macro_state_dir(child)
    )


def legacy_macro_state_dir(workspace_root: Path, state_id: str) -> Path:
    return workspace_root / state_id


def model_from_generation_run(run_dir: Path) -> str:
    settings_path = run_dir / SETTINGS_FILENAME
    if settings_path.exists():
        settings = load_json(settings_path)
        model = settings.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()

    metadata_path = run_dir / METADATA_FILENAME
    if metadata_path.exists():
        metadata = load_json(metadata_path)
        model = metadata.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()

    return "unknown"


def legacy_generations_dir(workspace_root: Path, state_id: str) -> Path:
    return legacy_macro_state_dir(workspace_root, state_id) / LEGACY_GENERATIONS_DIRNAME


def is_generation_run_dir(path: Path) -> bool:
    return path.is_dir() and (path / METADATA_FILENAME).exists()


def generation_run_status(run_dir: Path) -> str | None:
    metadata_path = run_dir / METADATA_FILENAME
    if not metadata_path.exists():
        return None
    metadata = load_json(metadata_path)
    status = metadata.get("status")
    return status if isinstance(status, str) else None


def is_in_progress_generation_run(run_dir: Path) -> bool:
    return generation_run_status(run_dir) == GENERATION_STATUS_IN_PROGRESS


def is_finalized_generation_run(run_dir: Path) -> bool:
    status = generation_run_status(run_dir)
    return status in FINAL_GENERATION_STATUSES


def find_resumable_generation_run(
    workspace_root: Path,
    state_id: str,
    *,
    model: str,
) -> Path | None:
    candidates = [
        run_dir
        for run_dir in list_model_run_dirs(workspace_root, state_id, model=model)
        if is_generation_run_dir(run_dir) and is_in_progress_generation_run(run_dir)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.name)


def load_generation_run_outputs(run_dir: Path) -> dict[str, dict[str, Any]]:
    metadata_path = run_dir / METADATA_FILENAME
    if not metadata_path.exists():
        return {}

    metadata = load_json(metadata_path)
    success_ids = metadata.get("successful_micro_action_ids")
    if not isinstance(success_ids, list):
        return {}

    outputs: dict[str, dict[str, Any]] = {}
    for action_id in success_ids:
        if not isinstance(action_id, str):
            continue
        output_path = run_dir / f"{action_id}.json"
        if not output_path.exists():
            continue
        payload = load_json(output_path)
        outputs[action_id] = {
            "micro_action_id": action_id,
            "task_type": payload["task_type"],
            "task": payload["task"],
        }
    return outputs


def load_generation_run_state(run_dir: Path) -> dict[str, Any]:
    metadata_path = run_dir / METADATA_FILENAME
    if not metadata_path.exists():
        raise FileNotFoundError(f"missing generation metadata: {metadata_path}")

    metadata = load_json(metadata_path)
    settings_path = run_dir / SETTINGS_FILENAME
    settings = load_json(settings_path) if settings_path.exists() else {}
    return {
        "metadata": metadata,
        "settings": settings,
        "outputs": load_generation_run_outputs(run_dir),
        "batch_results": list(metadata.get("batches", [])),
    }


def count_raw_response_batches(run_dir: Path) -> int:
    return sum(
        1
        for child in run_dir.iterdir()
        if child.is_file() and RAW_RESPONSE_BATCH_PATTERN.match(child.name)
    )


def estimate_total_batches(*, requested_count: int, batch_size: int | str | None) -> int:
    if requested_count <= 0:
        return 0
    if batch_size in (None, "all"):
        return 1
    size = int(batch_size)
    if size < 1:
        return 1
    return (requested_count + size - 1) // size


def list_model_run_dirs(
    workspace_root: Path,
    state_id: str,
    *,
    model: str,
) -> list[Path]:
    state_model_dir = macro_state_tasks_dir(workspace_root, state_id, model=model)
    if not state_model_dir.exists():
        return []
    return sorted(
        child
        for child in state_model_dir.iterdir()
        if child.is_dir() and RUN_TIMESTAMP_PATTERN.match(child.name)
    )


def is_in_flight_generation_run_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if is_in_progress_generation_run(path):
        return True
    if (path / METADATA_FILENAME).exists():
        return False
    return any(
        RAW_RESPONSE_BATCH_PATTERN.match(child.name)
        for child in path.iterdir()
        if child.is_file()
    )


def in_flight_microaction_ids_from_run(run_dir: Path) -> set[str]:
    ids: set[str] = set()
    for path in sorted(run_dir.iterdir()):
        if not path.is_file():
            continue
        if RAW_RESPONSE_BATCH_PATTERN.match(path.name) is None:
            continue
        try:
            payload = load_json(path)
        except (OSError, ValueError, TypeError):
            continue
        microactions = payload.get("microactions")
        if not isinstance(microactions, list):
            continue
        for entry in microactions:
            if not isinstance(entry, dict):
                continue
            micro_action_id = entry.get("micro_action_id")
            if isinstance(micro_action_id, str):
                ids.add(micro_action_id)
    return ids


def in_flight_generation_progress(
    *,
    workspace_root: Path,
    state_id: str,
    model: str,
) -> dict[str, object] | None:
    """Summarize the newest unfinished generation run."""
    resumable = find_resumable_generation_run(workspace_root, state_id, model=model)
    if resumable is not None:
        metadata = load_json(resumable / METADATA_FILENAME)
        batches = metadata.get("batches", [])
        batches_committed = len(batches) if isinstance(batches, list) else 0
        raw_batches = count_raw_response_batches(resumable)
        batch_in_progress = raw_batches > batches_committed
        requested_ids = metadata.get("requested_micro_action_ids", [])
        requested_count = len(requested_ids) if isinstance(requested_ids, list) else 0
        total_batches = estimate_total_batches(
            requested_count=requested_count,
            batch_size=metadata.get("batch_size"),
        )
        current_batch = batches_committed + (1 if batch_in_progress else 0)
        success_ids = metadata.get("successful_micro_action_ids", [])
        committed_count = len(success_ids) if isinstance(success_ids, list) else 0
        return {
            "run_dir": str(resumable),
            "microaction_count": 0,
            "micro_action_ids": [],
            "batches_done": current_batch,
            "latest_batch_index": current_batch,
            "batches_total": total_batches,
            "batch_in_progress": batch_in_progress,
            "committed_count": committed_count,
            "source": "metadata",
        }

    candidates = [
        run_dir
        for run_dir in list_model_run_dirs(workspace_root, state_id, model=model)
        if is_in_flight_generation_run_dir(run_dir)
    ]
    if not candidates:
        return None

    def run_activity_key(run_dir: Path) -> tuple[int, float, str]:
        batch_files = [
            child
            for child in run_dir.iterdir()
            if child.is_file() and RAW_RESPONSE_BATCH_PATTERN.match(child.name)
        ]
        latest_batch_index = 0
        latest_mtime = run_dir.stat().st_mtime
        if batch_files:
            latest_batch_index = max(
                int(RAW_RESPONSE_BATCH_PATTERN.match(child.name).group(1))
                for child in batch_files
            )
            latest_mtime = max(child.stat().st_mtime for child in batch_files)
        return latest_batch_index, latest_mtime, run_dir.name

    run_dir = max(candidates, key=run_activity_key)
    batch_files = sorted(
        child
        for child in run_dir.iterdir()
        if child.is_file() and RAW_RESPONSE_BATCH_PATTERN.match(child.name)
    )
    latest_batch_index = 0
    if batch_files:
        latest_batch_index = max(
            int(RAW_RESPONSE_BATCH_PATTERN.match(child.name).group(1))
            for child in batch_files
        )
    micro_action_ids = in_flight_microaction_ids_from_run(run_dir)
    return {
        "run_dir": str(run_dir),
        "microaction_count": len(micro_action_ids),
        "micro_action_ids": sorted(micro_action_ids),
        "batches_done": len(batch_files),
        "latest_batch_index": latest_batch_index,
        "batches_total": None,
        "batch_in_progress": False,
        "committed_count": 0,
        "source": "raw_response",
    }


def _collect_timestamp_run_dirs(parent: Path) -> list[Path]:
    if not parent.exists():
        return []
    return sorted(
        child
        for child in parent.iterdir()
        if child.is_dir()
        and RUN_TIMESTAMP_PATTERN.match(child.name)
        and is_generation_run_dir(child)
    )


def list_generation_runs(
    workspace_root: Path,
    state_id: str,
    *,
    model: str | None = None,
) -> list[Path]:
    runs: list[Path] = []
    tasks_root = workspace_root / TASK_GENERATION_DIRNAME
    if model is not None:
        runs.extend(
            _collect_timestamp_run_dirs(
                macro_state_tasks_dir(workspace_root, state_id, model=model),
            )
        )
    elif tasks_root.exists():
        for model_dir in tasks_root.iterdir():
            if not model_dir.is_dir():
                continue
            runs.extend(_collect_timestamp_run_dirs(model_dir / state_id))

    return sorted(runs, key=lambda path: (path.parent.parent.name, path.name))


def successful_action_ids_from_generation_run(run_dir: Path) -> set[str]:
    metadata_path = run_dir / METADATA_FILENAME
    if not metadata_path.exists():
        raise FileNotFoundError(f"missing generation metadata: {metadata_path}")

    metadata = load_json(metadata_path)
    success_ids = metadata.get("successful_micro_action_ids")
    if isinstance(success_ids, list):
        return {item for item in success_ids if isinstance(item, str)}

    success_entries = metadata.get("successful_microactions", [])
    if not isinstance(success_entries, list):
        return set()
    return {
        entry["micro_action_id"]
        for entry in success_entries
        if isinstance(entry, dict) and isinstance(entry.get("micro_action_id"), str)
    }


def successful_action_ids_from_runs(run_dirs: list[Path]) -> set[str]:
    successful_ids: set[str] = set()
    for run_dir in run_dirs:
        successful_ids.update(successful_action_ids_from_generation_run(run_dir))
    return successful_ids


def classified_action_keys(classification: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for bucket in YIELD_BUCKETS:
        bucket_ids = classification.get(bucket, [])
        if isinstance(bucket_ids, list):
            keys.update(item for item in bucket_ids if isinstance(item, str))
    return keys


def generation_coverage(
    *,
    workspace_root: Path,
    state_id: str,
    model: str | None = None,
    classification_model: str,
) -> dict[str, object]:
    classification_file = classification_path(
        workspace_root,
        state_id,
        classification_model=classification_model,
    )
    if not classification_file.exists():
        raise FileNotFoundError(f"missing classification file: {classification_file}")

    classification = load_json(classification_file)
    expected = classified_action_keys(classification)
    runs = list_generation_runs(workspace_root, state_id, model=model)
    successful = successful_action_ids_from_runs(runs)
    missing = expected - successful
    return {
        "state_id": state_id,
        "expected_count": len(expected),
        "successful_count": len(successful),
        "missing_ids": sorted(missing),
        "complete": not missing,
        "generation_runs": [str(path) for path in runs],
        "model": model,
        "classification_model": classification_model,
    }


def build_settings_payload(
    *,
    timestamp: str,
    macro_state_id: str,
    micro_action_ids: list[str],
    openai_config: dict[str, str],
    creative: bool,
    completion_params: dict[str, Any],
    usage: dict[str, Any] | None = None,
    status: str = "generated",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": timestamp,
        "status": status,
        "macro_state_id": macro_state_id,
        "micro_action_ids": micro_action_ids,
        "model": openai_config.get("model"),
        "base_url": openai_config.get("base_url"),
        "creative": creative,
        "completion_params": completion_params,
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


def write_microaction_outputs(
    run_dir: Path,
    outputs: dict[str, dict[str, Any]],
    *,
    only_action_ids: set[str] | None = None,
) -> None:
    for action_id, output in sorted(outputs.items()):
        if only_action_ids is not None and action_id not in only_action_ids:
            continue
        save_json(
            run_dir / f"{action_id}.json",
            {
                "micro_action_id": action_id,
                "task_type": output["task_type"],
                "task": output["task"],
            },
        )


def commit_generation_checkpoint(
    *,
    run_dir: Path,
    settings: dict[str, Any],
    metadata: dict[str, Any],
    new_outputs: dict[str, dict[str, Any]] | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    save_json(run_dir / SETTINGS_FILENAME, settings)
    save_json(run_dir / METADATA_FILENAME, metadata)
    if new_outputs:
        write_microaction_outputs(run_dir, new_outputs)


def write_generation_run(
    *,
    run_dir: Path,
    settings: dict[str, Any],
    metadata: dict[str, Any],
    outputs: dict[str, dict[str, Any]],
) -> None:
    commit_generation_checkpoint(
        run_dir=run_dir,
        settings=settings,
        metadata=metadata,
        new_outputs=outputs,
    )


def rewrite_generation_run_paths(run_dir: Path) -> None:
    """Rewrite embedded absolute paths after a generation run directory move."""
    for filename in (SETTINGS_FILENAME, METADATA_FILENAME):
        path = run_dir / filename
        if not path.exists():
            continue
        payload = load_json(path)
        if payload.get("generation_run"):
            payload["generation_run"] = str(run_dir)
        batches = payload.get("batches")
        if isinstance(batches, list):
            for batch in batches:
                if not isinstance(batch, dict):
                    continue
                raw_path = batch.get("raw_response_path")
                if isinstance(raw_path, str) and raw_path:
                    batch["raw_response_path"] = str(run_dir / Path(raw_path).name)
        save_json(path, payload)


def migrate_generation_run_layout(
    run_dir: Path,
    *,
    workspace_root: Path,
    default_model: str = "unknown",
) -> Path | None:
    """Move a run to {workspace_root}/task_generation/{model}/{macro_state_id}/{timestamp}/."""
    if not is_generation_run_dir(run_dir) and not is_in_flight_generation_run_dir(run_dir):
        return None

    model = model_from_generation_run(run_dir)
    if model == "unknown":
        model = default_model

    state_id: str | None = None
    metadata_path = run_dir / METADATA_FILENAME
    if metadata_path.exists():
        metadata = load_json(metadata_path)
        macro_state_id = metadata.get("macro_state_id")
        if isinstance(macro_state_id, str) and macro_state_id.strip():
            state_id = macro_state_id.strip()

    if state_id is None:
        ancestors = list(run_dir.parents)
        if run_dir.parent.name == LEGACY_GENERATIONS_DIRNAME:
            state_id = run_dir.parent.parent.name
        elif (
            len(ancestors) >= 3
            and ancestors[1].name == LEGACY_GENERATIONS_DIRNAME
            and ancestors[2].parent == workspace_root
        ):
            state_id = ancestors[2].name
        elif len(ancestors) >= 2 and ancestors[1].parent.name in {
            TASK_GENERATION_DIRNAME,
            model_dir_name(model),
        }:
            state_id = ancestors[1].name
        elif (
            len(ancestors) >= 2
            and ancestors[1].parent == workspace_root
            and ancestors[1].name != CLASSIFICATION_DIRNAME
            and ancestors[1].name != TASK_GENERATION_DIRNAME
        ):
            state_id = ancestors[1].name

    if state_id is None:
        raise ValueError(f"cannot infer macro state id for generation run: {run_dir}")

    target = generation_run_dir(
        workspace_root,
        state_id,
        model=model,
        timestamp=run_dir.name,
    )
    if target == run_dir:
        rewrite_generation_run_paths(run_dir)
        return run_dir
    if target.exists():
        raise FileExistsError(f"cannot migrate {run_dir} because {target} already exists")

    target.parent.mkdir(parents=True, exist_ok=True)
    run_dir.rename(target)
    rewrite_generation_run_paths(target)
    return target


def migrate_legacy_generation_run(run_dir: Path, *, default_model: str = "unknown") -> Path | None:
    """Backward-compatible alias for older migration callers."""
    workspace_root = run_dir
    while workspace_root.parent != workspace_root:
        if (workspace_root / CLASSIFICATION_DIRNAME).exists() or (workspace_root / TASK_GENERATION_DIRNAME).exists():
            break
        if any(
            is_legacy_flat_classification_state_dir(child, workspace_root=workspace_root)
            for child in workspace_root.iterdir()
            if child.is_dir()
        ):
            break
        workspace_root = workspace_root.parent
    else:
        return None
    return migrate_generation_run_layout(
        run_dir,
        workspace_root=workspace_root,
        default_model=default_model,
    )
