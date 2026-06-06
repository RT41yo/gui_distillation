from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.pricing import UsageCost

COST_CLASSIFICATION_LOG = "cost_classification.jsonl"
COST_TASK_GENERATION_LOG = "cost_task_generation.jsonl"


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
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        entity_field: entity_id,
        "model": model,
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
        ),
    )
    return path


def log_task_generation_batch_cost(
    output_root: Path,
    macro_state_id: str,
    model: str,
    usage_cost: UsageCost,
    *,
    generation_run: str | None = None,
) -> Path:
    path = output_root / COST_TASK_GENERATION_LOG
    record = build_cost_record(
        entity_id=macro_state_id,
        entity_field="macro_action_id",
        model=model,
        usage_cost=usage_cost,
    )
    if generation_run is not None:
        record["generation_run"] = generation_run
    append_cost_log(path, record)
    return path
