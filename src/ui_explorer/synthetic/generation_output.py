from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.io import load_json, save_json
from ui_explorer.synthetic.schemas import YIELD_BUCKETS

GENERATIONS_DIRNAME = "generations"
SETTINGS_FILENAME = "settings.json"
METADATA_FILENAME = "metadata.json"
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


def classification_path(classification_root: Path, state_id: str) -> Path:
    return classification_root / state_id / "yield_classification.json"


def generation_run_dir(
    classification_root: Path,
    state_id: str,
    *,
    model: str,
    timestamp: str | None = None,
) -> Path:
    run_id = timestamp or utc_run_timestamp()
    return (
        classification_root
        / state_id
        / GENERATIONS_DIRNAME
        / model_dir_name(model)
        / run_id
    )


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


def generations_dir(classification_root: Path, state_id: str) -> Path:
    return classification_root / state_id / GENERATIONS_DIRNAME


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
    classification_root: Path,
    state_id: str,
    *,
    model: str,
) -> Path | None:
    candidates = [
        run_dir
        for run_dir in list_model_run_dirs(classification_root, state_id, model=model)
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


def model_generations_dir(
    classification_root: Path,
    state_id: str,
    *,
    model: str,
) -> Path:
    return generations_dir(classification_root, state_id) / model_dir_name(model)


def list_model_run_dirs(
    classification_root: Path,
    state_id: str,
    *,
    model: str,
) -> list[Path]:
    model_dir = model_generations_dir(classification_root, state_id, model=model)
    if not model_dir.exists():
        return []
    return sorted(
        child
        for child in model_dir.iterdir()
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
    classification_root: Path,
    state_id: str,
    model: str,
) -> dict[str, object] | None:
    """Summarize the newest unfinished generation run."""
    resumable = find_resumable_generation_run(classification_root, state_id, model=model)
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
        for run_dir in list_model_run_dirs(classification_root, state_id, model=model)
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


def list_generation_runs(
    classification_root: Path,
    state_id: str,
    *,
    model: str | None = None,
) -> list[Path]:
    runs_dir = generations_dir(classification_root, state_id)
    if not runs_dir.exists():
        return []

    runs: list[Path] = []
    for child in runs_dir.iterdir():
        if not child.is_dir():
            continue
        if is_generation_run_dir(child):
            runs.append(child)
            continue
        for run_dir in child.iterdir():
            if is_generation_run_dir(run_dir):
                runs.append(run_dir)

    runs = sorted(runs, key=lambda path: (path.parent.name, path.name))
    if model is None:
        return runs
    model_name = model_dir_name(model)
    return [run_dir for run_dir in runs if run_dir.parent.name == model_name]


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
    classification_root: Path,
    state_id: str,
    model: str | None = None,
) -> dict[str, object]:
    classification_file = classification_path(classification_root, state_id)
    if not classification_file.exists():
        raise FileNotFoundError(f"missing classification file: {classification_file}")

    classification = load_json(classification_file)
    expected = classified_action_keys(classification)
    runs = list_generation_runs(classification_root, state_id, model=model)
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


def migrate_legacy_generation_run(run_dir: Path, *, default_model: str = "unknown") -> Path | None:
    """Move a flat generations/{timestamp} run to generations/{model}/{timestamp}."""
    if not is_generation_run_dir(run_dir):
        return None
    if run_dir.parent.name != GENERATIONS_DIRNAME:
        return run_dir

    model = model_from_generation_run(run_dir)
    if model == "unknown":
        model = default_model

    target = run_dir.parent / model_dir_name(model) / run_dir.name
    if target == run_dir:
        return run_dir
    if target.exists():
        raise FileExistsError(f"cannot migrate {run_dir} because {target} already exists")

    target.parent.mkdir(parents=True, exist_ok=True)
    run_dir.rename(target)

    for filename in (SETTINGS_FILENAME, METADATA_FILENAME):
        path = target / filename
        if not path.exists():
            continue
        payload = load_json(path)
        payload["generation_run"] = str(target)
        if filename == METADATA_FILENAME and "model" not in payload:
            payload["model"] = model
        save_json(path, payload)

    return target
