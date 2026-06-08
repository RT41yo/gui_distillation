from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.pricing import UsageCost

COST_CLASSIFICATION_LOG = "cost_classification.jsonl"
COST_TASK_GENERATION_LOG = "cost_task_generation.jsonl"
LEGACY_COST_GOAL_GENERATION_LOG = "cost_goal_generation.jsonl"


def append_cost_log(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_cost_record(
    *,
    entity_id: str,
    entity_field: str,
    model: str,
    usage_cost: UsageCost,
    prompt: str,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        entity_field: entity_id,
        "model": model,
        "prompt": prompt,
        "num_tokens": usage_cost.num_tokens,
        "cost": usage_cost.cost_usd,
    }


def log_classification_cost(
    output_root: Path,
    macro_state_id: str,
    model: str,
    usage_cost: UsageCost,
) -> Path:
    path = output_root / COST_CLASSIFICATION_LOG
    append_cost_log(
        path,
        build_cost_record(
            entity_id=macro_state_id,
            entity_field="macro_action_id",
            model=model,
            usage_cost=usage_cost,
            prompt="classification",
        ),
    )
    return path


def log_task_generation_batch_cost(
    output_root: Path,
    macro_state_id: str,
    model: str,
    usage_cost: UsageCost,
    *,
    prompt: str = "task",
    generation_run: str | None = None,
) -> Path:
    path = output_root / COST_TASK_GENERATION_LOG
    record = build_cost_record(
        entity_id=macro_state_id,
        entity_field="macro_action_id",
        model=model,
        usage_cost=usage_cost,
        prompt=prompt,
    )
    if generation_run is not None:
        record["generation_run"] = generation_run
    append_cost_log(path, record)
    return path


def reconcile_cost_log_prompts(workspace_root: Path) -> dict[str, int]:
    task_log = workspace_root / COST_TASK_GENERATION_LOG
    legacy_goal_log = workspace_root / LEGACY_COST_GOAL_GENERATION_LOG
    records: list[dict[str, Any]] = []
    merged_from_legacy_goal = 0
    fixed_task_prompt = 0

    if task_log.exists():
        for line in task_log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))

    if legacy_goal_log.exists():
        for line in legacy_goal_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            record["prompt"] = "goal"
            records.append(record)
            merged_from_legacy_goal += 1
        legacy_goal_log.unlink()

    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record.get("prompt"), str) or not record["prompt"].strip():
            record["prompt"] = "goal" if _looks_like_goal_generation_run(record) else "task"
            fixed_task_prompt += 1
        normalized.append(record)

    task_log.write_text(
        ("\n".join(json.dumps(record, ensure_ascii=False) for record in normalized) + "\n")
        if normalized
        else "",
        encoding="utf-8",
    )
    return {
        "merged_from_legacy_goal": merged_from_legacy_goal,
        "fixed_prompt": fixed_task_prompt,
    }


def _looks_like_goal_generation_run(record: dict[str, Any]) -> bool:
    generation_run = record.get("generation_run")
    if isinstance(generation_run, str) and "/goal_generation/" in generation_run.replace("\\", "/"):
        return True
    return "source_task_generation_run" in record
