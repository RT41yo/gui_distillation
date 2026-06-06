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

TASK_TYPES: tuple[str, ...] = (
    "selection_transform",
    "cursor_format_toggle",
    "paragraph_layout",
    "insert_at_cursor",
    "dialog_open",
    "document_analysis",
    "list_manipulation",
    "table_structure",
    "table_content",
    "language_spelling_setting",
    "view_or_zoom",
    "style_management",
    "review_commenting",
    "availability_check",
    "unsafe_or_external_observation",
)

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
                        "task_type": {
                            "type": "string",
                            "enum": list(TASK_TYPES),
                        },
                        "task": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "instruction": {"type": "string"},
                                    "expected_outcome": {"type": "string"},
                                    "preconditions": {
                                        "type": "object",
                                        "properties": {
                                            "description": {"type": "string"},
                                            "extras": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "key": {"type": "string"},
                                                        "value": {"type": "string"},
                                                    },
                                                    "required": ["key", "value"],
                                                    "additionalProperties": False,
                                                },
                                            },
                                        },
                                        "required": ["description", "extras"],
                                        "additionalProperties": False,
                                    },
                                },
                                "required": ["instruction", "expected_outcome", "preconditions"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["micro_action_id", "task_type", "task"],
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
) -> dict[str, dict[str, Any]]:
    entries = result.get("microactions")
    if not isinstance(entries, list):
        raise ValueError("microactions must be an array")

    outputs: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each microactions entry must be an object")
        action_id = entry.get("micro_action_id")
        task_type = entry.get("task_type")
        tasks = entry.get("task")
        if not isinstance(action_id, str):
            raise ValueError("micro_action_id must be a string")
        if action_id in seen:
            raise ValueError(f"duplicate micro_action_id in batch output: {action_id}")
        seen.add(action_id)
        if not isinstance(task_type, str) or task_type not in TASK_TYPES:
            raise ValueError(
                f"task_type for {action_id} must be one of: {', '.join(TASK_TYPES)}"
            )
        if not isinstance(tasks, list) or not tasks:
            raise ValueError(f"task list for {action_id} must be a non-empty array")
        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                raise ValueError(f"task {index} for {action_id} must be an object")
            instruction = task.get("instruction")
            expected_outcome = task.get("expected_outcome")
            preconditions = task.get("preconditions")
            if not isinstance(instruction, str) or not instruction.strip():
                raise ValueError(f"task {index} for {action_id} must include instruction")
            if not isinstance(expected_outcome, str) or not expected_outcome.strip():
                raise ValueError(
                    f"task {index} for {action_id} must include expected_outcome"
                )
            if not isinstance(preconditions, dict):
                raise ValueError(f"task {index} for {action_id} must include preconditions")
            description = preconditions.get("description")
            extras = preconditions.get("extras")
            if not isinstance(description, str) or not description.strip():
                raise ValueError(
                    f"task {index} for {action_id} must include preconditions.description"
                )
            if not isinstance(extras, list):
                raise ValueError(
                    f"task {index} for {action_id} must include preconditions.extras"
                )
            for extra in extras:
                if not isinstance(extra, dict):
                    raise ValueError(
                        f"preconditions.extras for task {index} of {action_id} "
                        "must contain objects"
                    )
                key = extra.get("key")
                value = extra.get("value")
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(
                        f"preconditions.extras key for task {index} of {action_id} "
                        "must be a non-empty string"
                    )
                if not isinstance(value, str):
                    raise ValueError(
                        f"preconditions.extras value for task {index} of {action_id} "
                        "must be a string"
                    )
        outputs[action_id] = {"task_type": task_type, "task": tasks}

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
