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

_SETUP_REQUIREMENTS_SCHEMA: dict[str, Any] = {
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
                                    "preconditions": _SETUP_REQUIREMENTS_SCHEMA,
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

MACROSTATE_GOALS_BATCH_SCHEMA: dict[str, Any] = {
    "name": "macrostate_goals_batch",
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
                        "goal": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "task_index": {"type": "integer"},
                                    "variants": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "goal": {"type": "string"},
                                                "expected_outcome": {"type": "string"},
                                            },
                                            "required": ["goal", "expected_outcome"],
                                            "additionalProperties": False,
                                        },
                                    },
                                },
                                "required": ["task_index", "variants"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["micro_action_id", "task_type", "goal"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["microactions"],
        "additionalProperties": False,
    },
}


def generation_payload_key(kind: str) -> str:
    if kind == "goal":
        return "goal"
    if kind == "task":
        return "task"
    raise ValueError(f"unknown generation kind {kind!r}")


def generation_text_field(kind: str) -> str:
    if kind == "goal":
        return "goal"
    if kind == "task":
        return "instruction"
    raise ValueError(f"unknown generation kind {kind!r}")


def generation_setup_field(kind: str) -> str:
    if kind == "task":
        return "preconditions"
    raise ValueError(f"unknown generation kind {kind!r}")


def normalize_yield_classification(
    result: dict[str, Any],
    expected_action_keys: set[str],
    *,
    fill_missing_bucket: str = "low",
) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {bucket: [] for bucket in YIELD_BUCKETS}
    seen: set[str] = set()
    for bucket in YIELD_BUCKETS:
        ids = result.get(bucket, [])
        if not isinstance(ids, list):
            continue
        for action_id in ids:
            if not isinstance(action_id, str):
                continue
            if action_id not in expected_action_keys or action_id in seen:
                continue
            normalized[bucket].append(action_id)
            seen.add(action_id)

    missing = expected_action_keys - seen
    if missing and fill_missing_bucket in YIELD_BUCKETS:
        normalized[fill_missing_bucket].extend(sorted(missing))
    return normalized


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


def validate_macrostate_goals_batch(
    result: dict[str, Any],
    expected_action_keys: set[str],
    *,
    expected_goal_counts: dict[str, int] | None = None,
    max_variant_count: int | None = None,
) -> dict[str, dict[str, Any]]:
    entries = result.get("microactions")
    if not isinstance(entries, list):
        raise ValueError("microactions must be an array")

    outputs: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each microactions entry must be an object")
        action_id = entry.get("micro_action_id")
        task_type = entry.get("task_type")
        goals = entry.get("goal")
        if not isinstance(action_id, str):
            raise ValueError("micro_action_id must be a string")
        if action_id in seen:
            raise ValueError(f"duplicate micro_action_id in batch output: {action_id}")
        seen.add(action_id)
        if not isinstance(task_type, str) or task_type not in TASK_TYPES:
            raise ValueError(
                f"task_type for {action_id} must be one of: {', '.join(TASK_TYPES)}"
            )
        if not isinstance(goals, list) or not goals:
            raise ValueError(f"goal list for {action_id} must be a non-empty array")
        if expected_goal_counts is not None:
            required_count = expected_goal_counts.get(action_id)
            if required_count is not None and len(goals) != required_count:
                raise ValueError(
                    f"goal list for {action_id} must contain exactly {required_count} "
                    f"item(s), got {len(goals)}"
                )
        seen_task_indexes: set[int] = set()
        for index, goal_entry in enumerate(goals):
            if not isinstance(goal_entry, dict):
                raise ValueError(f"goal {index} for {action_id} must be an object")
            task_index = goal_entry.get("task_index")
            if not isinstance(task_index, int) or task_index < 0:
                raise ValueError(f"goal {index} for {action_id} must include task_index")
            if task_index in seen_task_indexes:
                raise ValueError(
                    f"duplicate task_index {task_index} in goal list for {action_id}"
                )
            seen_task_indexes.add(task_index)
            variants = goal_entry.get("variants")
            if not isinstance(variants, list) or not variants:
                raise ValueError(
                    f"goal {index} for {action_id} must include a non-empty variants array"
                )
            if max_variant_count is not None and len(variants) > max_variant_count:
                raise ValueError(
                    f"goal {index} for {action_id} has {len(variants)} variant(s); "
                    f"maximum is {max_variant_count}"
                )
            seen_variant_goals: set[str] = set()
            for variant_index, variant in enumerate(variants):
                if not isinstance(variant, dict):
                    raise ValueError(
                        f"variant {variant_index} for goal {index} of {action_id} must be an object"
                    )
                goal_text = variant.get("goal")
                expected_outcome = variant.get("expected_outcome")
                if not isinstance(goal_text, str) or not goal_text.strip():
                    raise ValueError(
                        f"variant {variant_index} for goal {index} of {action_id} must include goal"
                    )
                normalized_goal = goal_text.strip().casefold()
                if normalized_goal in seen_variant_goals:
                    raise ValueError(
                        f"duplicate variant goal for task_index {task_index} of {action_id}: "
                        f"{goal_text!r}"
                    )
                seen_variant_goals.add(normalized_goal)
                if not isinstance(expected_outcome, str) or not expected_outcome.strip():
                    raise ValueError(
                        f"variant {variant_index} for goal {index} of {action_id} "
                        "must include expected_outcome"
                    )
        outputs[action_id] = {"task_type": task_type, "goal": goals}

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
