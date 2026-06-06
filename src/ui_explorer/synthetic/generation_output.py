from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.io import save_json

GENERATIONS_DIRNAME = "generations"
SETTINGS_FILENAME = "settings.json"
METADATA_FILENAME = "metadata.json"


def utc_run_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def classification_path(classification_root: Path, state_id: str) -> Path:
    return classification_root / state_id / "yield_classification.json"


def generation_run_dir(classification_root: Path, state_id: str, timestamp: str | None = None) -> Path:
    run_id = timestamp or utc_run_timestamp()
    return classification_root / state_id / GENERATIONS_DIRNAME / run_id


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


def write_generation_run(
    *,
    run_dir: Path,
    settings: dict[str, Any],
    metadata: dict[str, Any],
    outputs: dict[str, dict[str, Any]],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    save_json(run_dir / SETTINGS_FILENAME, settings)
    save_json(run_dir / METADATA_FILENAME, metadata)
    for action_id, output in sorted(outputs.items()):
        save_json(
            run_dir / f"{action_id}.json",
            {
                "micro_action_id": action_id,
                "task_type": output["task_type"],
                "task": output["task"],
            },
        )
