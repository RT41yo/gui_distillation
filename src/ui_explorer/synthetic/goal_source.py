from __future__ import annotations

from pathlib import Path
from typing import Any

from ui_explorer.synthetic.generation_output import (
    existing_goal_variant_counts,
    is_finalized_generation_run,
    list_generation_runs,
    load_generation_run_outputs,
)
from ui_explorer.synthetic.osworld_conversion import deterministic_task_id
from ui_explorer.synthetic.scope_index import ScopeIndex
from ui_explorer.synthetic.writer_macrostate_setup import build_writer_macrostate_preflight


def find_latest_task_generation_run(
    workspace_root: Path,
    state_id: str,
    *,
    model: str | None = None,
) -> Path | None:
    runs = list_generation_runs(workspace_root, state_id, model=model)
    finalized = [run_dir for run_dir in runs if is_finalized_generation_run(run_dir)]
    if not finalized:
        return None
    return max(finalized, key=lambda path: path.name)


def build_preflight_trajectory_context(
    index: ScopeIndex,
    *,
    state_id: str,
) -> dict[str, Any]:
    slim_macro = index.build_slim_macro_context(state_id)
    scope_state = index.get_scope_state(state_id)
    active_root = scope_state.get("recomputed_active_root") or scope_state.get("graph_active_root") or {}
    _, macrostate_setup = build_writer_macrostate_preflight(
        index,
        macro_state_id=state_id,
        vm_document_path="/home/user/Desktop/synthetic_writer_preflight_context.docx",
    )
    if not isinstance(macrostate_setup, dict):
        macrostate_setup = {"status": "unsupported"}
    return {
        "macro_state_id": state_id,
        "macro_path_text": slim_macro["macro_path_text"],
        "active_root": {
            "kind": active_root.get("kind"),
            "role": active_root.get("role"),
            "name": active_root.get("name"),
        },
        "macrostate_setup": macrostate_setup,
    }


def source_tasks_for_action_keys(
    source_outputs: dict[str, dict[str, Any]],
    action_keys: set[str],
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for action_id in sorted(action_keys):
        payload = source_outputs.get(action_id)
        if not isinstance(payload, dict):
            continue
        tasks = payload.get("task")
        if not isinstance(tasks, list) or not tasks:
            continue
        selected[action_id] = {
            "micro_action_id": action_id,
            "task_type": payload["task_type"],
            "task": tasks,
        }
    return selected


def build_goal_target_payload(
    *,
    index: ScopeIndex,
    state_id: str,
    scope_state: dict[str, Any],
    action_keys: set[str],
    source_outputs: dict[str, dict[str, Any]],
    preflight_context: dict[str, Any],
    prompt_profile: str,
    goal_variant_count: int,
) -> list[dict[str, Any]]:
    by_key = {
        action["action_key"]: action
        for action in scope_state.get("active_root_micro_actions", [])
    }
    selected_sources = source_tasks_for_action_keys(source_outputs, action_keys)

    targets: list[dict[str, Any]] = []
    for action_key in sorted(action_keys):
        source = selected_sources.get(action_key)
        if source is None:
            continue
        micro_action = by_key.get(action_key)
        if micro_action is None:
            raise KeyError(f"micro_action_id {action_key} not found in scope state {state_id}")

        source_tasks = [
            {
                "task_index": task_index,
                "instruction": task_entry["instruction"],
                "preconditions": task_entry["preconditions"],
                "expected_outcome": task_entry["expected_outcome"],
            }
            for task_index, task_entry in enumerate(source["task"])
            if isinstance(task_entry, dict)
        ]
        entry: dict[str, Any] = {
            "micro_action_id": action_key,
            "task_type": source["task_type"],
            "goal_count_required": len(source_tasks),
            "goal_variant_count_required": goal_variant_count,
            "preflight_trajectory_context": preflight_context,
            "source_tasks": source_tasks,
        }
        if prompt_profile == "slim":
            entry["name"] = micro_action.get("name")
            entry["role"] = micro_action.get("role")
            if micro_action.get("is_enabled") is False:
                entry["is_enabled"] = False
        else:
            entry.update({
                "role": micro_action.get("role"),
                "name": micro_action.get("name"),
                "description": micro_action.get("description"),
                "bbox": micro_action.get("bbox"),
                "is_showing": micro_action.get("is_showing"),
                "is_enabled": micro_action.get("is_enabled"),
                "is_sensitive": micro_action.get("is_sensitive"),
                "reason": micro_action.get("reason"),
            })
        targets.append(entry)
    return targets


def required_goal_task_ids(
    *,
    run_timestamp: str,
    source_outputs: dict[str, dict[str, Any]],
    action_keys: set[str],
) -> dict[str, set[str]]:
    required: dict[str, set[str]] = {}
    for action_id in sorted(action_keys):
        payload = source_outputs.get(action_id)
        if not isinstance(payload, dict):
            continue
        tasks = payload.get("task")
        if not isinstance(tasks, list) or not tasks:
            continue
        required[action_id] = {
            deterministic_task_id(
                run_timestamp=run_timestamp,
                micro_action_id=action_id,
                task_index=task_index,
            )
            for task_index in range(len(tasks))
        }
    return required


def filter_microactions_with_complete_goals(
    run_dir: Path,
    action_keys: set[str],
    source_outputs: dict[str, dict[str, Any]],
    *,
    goal_variant_count: int,
) -> tuple[set[str], dict[str, list[str]]]:
    existing = existing_goal_variant_counts(run_dir)
    required_by_action = required_goal_task_ids(
        run_timestamp=run_dir.name,
        source_outputs=source_outputs,
        action_keys=action_keys,
    )
    remaining: set[str] = set()
    skipped: dict[str, list[str]] = {}
    for action_id in sorted(action_keys):
        required = required_by_action.get(action_id, set())
        if not required:
            continue
        complete = all(
            existing.get(task_id, 0) >= goal_variant_count for task_id in required
        )
        if complete:
            skipped[action_id] = sorted(required)
        else:
            remaining.add(action_id)
    return remaining, skipped


def enrich_goal_outputs(
    outputs: dict[str, dict[str, Any]],
    *,
    source_outputs: dict[str, dict[str, Any]],
    source_task_generation_run: str,
    run_timestamp: str,
) -> dict[str, dict[str, Any]]:
    enriched: dict[str, dict[str, Any]] = {}
    for action_id, output in outputs.items():
        source = source_outputs.get(action_id)
        if not isinstance(source, dict):
            enriched[action_id] = output
            continue
        source_tasks = source.get("task", [])
        goals = output.get("goal", [])
        merged_goals: list[dict[str, Any]] = []
        for goal_entry in goals:
            if not isinstance(goal_entry, dict):
                continue
            task_index = goal_entry.get("task_index")
            source_task = None
            if isinstance(task_index, int) and 0 <= task_index < len(source_tasks):
                source_task = source_tasks[task_index]
            task_id = None
            if isinstance(task_index, int) and task_index >= 0:
                task_id = deterministic_task_id(
                    run_timestamp=run_timestamp,
                    micro_action_id=action_id,
                    task_index=task_index,
                )
            variants = goal_entry.get("variants")
            if not isinstance(variants, list):
                continue
            merged_variants: list[dict[str, Any]] = []
            for variant_index, variant in enumerate(variants):
                if not isinstance(variant, dict):
                    continue
                merged_variants.append({
                    "variant_index": variant_index,
                    "goal": variant["goal"],
                    "expected_outcome": variant["expected_outcome"],
                })
            merged: dict[str, Any] = {
                "task_index": task_index,
                "id": task_id,
                "variants": merged_variants,
            }
            if source_task is not None:
                merged["source_task"] = source_task
            merged_goals.append(merged)
        enriched[action_id] = {
            "micro_action_id": action_id,
            "task_type": output["task_type"],
            "goal": merged_goals,
        }
    return enriched
