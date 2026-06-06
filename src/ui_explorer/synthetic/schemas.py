from __future__ import annotations

from typing import Any

YIELD_BUCKETS = ("high", "medium", "low")

YIELD_GUIDANCE: dict[str, str] = {
    "high": (
        "Dialog openers with clear A11Y title, inspect/report tools, formatting dialogs, "
        "search/find flows, symbol insertion, list/format commands with visible document effect."
    ),
    "medium": (
        "Content-changing menu items with partial A11Y visibility, toolbar toggles, "
        "commands needing simple document preconditions."
    ),
    "low": (
        "Ambiguous labels, duplicate/no-op-prone actions, commands needing heavy setup, "
        "root toolbar shortcuts, or weak verifiability from A11Y alone."
    ),
}

TASK_COUNT_GUIDANCE: dict[str, str] = {
    "high": "10-15",
    "medium": "5-10",
    "low": "2-4",
}

YIELD_CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "name": "yield_classification",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "high": {
                "type": "array",
                "items": {"type": "string"},
            },
            "medium": {
                "type": "array",
                "items": {"type": "string"},
            },
            "low": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["high", "medium", "low"],
        "additionalProperties": False,
    },
}

MICROACTION_TASKS_SCHEMA: dict[str, Any] = {
    "name": "microaction_tasks",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "micro_action_id": {"type": "string"},
            "task": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["micro_action_id", "task"],
        "additionalProperties": False,
    },
}

MACROSTATE_TASKS_BATCH_SCHEMA: dict[str, Any] = {
    "name": "macrostate_tasks_batch",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "microactions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "micro_action_id": {"type": "string"},
                        "task": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["micro_action_id", "task"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["microactions"],
        "additionalProperties": False,
    },
}


def validate_yield_classification(
    result: dict[str, Any],
    expected_action_keys: set[str],
) -> None:
    keys = set(result.keys())
    if keys != set(YIELD_BUCKETS):
        raise ValueError(f"expected keys {YIELD_BUCKETS}, got {sorted(keys)}")

    seen: set[str] = set()
    classified: set[str] = set()
    for bucket in YIELD_BUCKETS:
        ids = result.get(bucket, [])
        if not isinstance(ids, list):
            raise ValueError(f"{bucket} must be a list")
        for action_id in ids:
            if not isinstance(action_id, str):
                raise ValueError(f"{bucket} contains non-string id: {action_id!r}")
            if action_id in seen:
                raise ValueError(f"duplicate micro_action_id across buckets: {action_id}")
            seen.add(action_id)
            classified.add(action_id)

    if classified != expected_action_keys:
        missing = expected_action_keys - classified
        extra = classified - expected_action_keys
        parts: list[str] = []
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if extra:
            parts.append(f"extra: {sorted(extra)}")
        raise ValueError("; ".join(parts))


def find_yield_bucket(classification: dict[str, Any], micro_action_id: str) -> str | None:
    for bucket in YIELD_BUCKETS:
        if micro_action_id in classification.get(bucket, []):
            return bucket
    return None


def validate_macrostate_tasks_batch(
    result: dict[str, Any],
    expected_action_keys: set[str],
) -> dict[str, list[str]]:
    entries = result.get("microactions")
    if not isinstance(entries, list):
        raise ValueError("microactions must be an array")

    outputs: dict[str, list[str]] = {}
    seen: set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each microactions entry must be an object")
        action_id = entry.get("micro_action_id")
        tasks = entry.get("task")
        if not isinstance(action_id, str):
            raise ValueError("micro_action_id must be a string")
        if action_id in seen:
            raise ValueError(f"duplicate micro_action_id in batch output: {action_id}")
        seen.add(action_id)
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"task list for {action_id} must be a non-empty array")
        if not all(isinstance(task, str) and task.strip() for task in tasks):
            raise ValueError(f"task list for {action_id} must contain non-empty strings")
        outputs[action_id] = tasks

    if seen != expected_action_keys:
        missing = expected_action_keys - seen
        extra = seen - expected_action_keys
        parts: list[str] = []
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if extra:
            parts.append(f"extra: {sorted(extra)}")
        raise ValueError("; ".join(parts))

    return outputs
