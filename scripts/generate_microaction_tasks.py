#!/usr/bin/env python3
"""Generate task instructions for classified microactions (batched per macro state)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.cost_log import log_task_generation_batch_cost
from ui_explorer.synthetic.env import load_env_file, resolve_openai_config
from ui_explorer.synthetic.generation_output import (
    GENERATION_STATUS_FAILED,
    GENERATION_STATUS_GENERATED,
    GENERATION_STATUS_IN_PROGRESS,
    GENERATION_STATUS_PARTIAL,
    build_settings_payload,
    classification_path,
    commit_generation_checkpoint,
    generation_run_dir,
    raw_batch_path,
    resolve_classification_model,
    is_in_progress_generation_run,
    load_generation_run_state,
    successful_action_ids_from_generation_run,
    utc_run_timestamp,
)
from ui_explorer.synthetic.io import load_json
from ui_explorer.synthetic.llm_args import CompletionParams, add_completion_args, completion_params_from_args
from ui_explorer.synthetic.logging_config import configure_logging
from ui_explorer.synthetic.openai_client import build_openai_messages, openai_structured_completion
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, repo_root, resolve_repo_path
from ui_explorer.synthetic.pricing import UsageCost
from ui_explorer.synthetic.timing import StageTimer
from ui_explorer.synthetic.schemas import (
    MACROSTATE_TASKS_BATCH_SCHEMA,
    TASK_COUNT_GUIDANCE,
    YIELD_BUCKETS,
    find_yield_bucket,
    validate_macrostate_tasks_batch,
)
from ui_explorer.synthetic.scope_index import (
    ScopeIndex,
    load_prompt_template_for_profile,
    render_prompt,
)

log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 6
DEFAULT_MAX_TOKENS = 16000
DEFAULT_PROMPT_PROFILE = "slim"
PROMPT_PROFILES = ("default", "slim")


def load_classification(
    workspace_root: Path,
    state_id: str,
    *,
    classification_model: str,
) -> dict[str, Any]:
    path = classification_path(
        workspace_root,
        state_id,
        classification_model=classification_model,
    )
    if not path.exists():
        raise FileNotFoundError(f"missing classification file: {path}")
    return load_json(path)


def classified_action_keys(classification: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for bucket in YIELD_BUCKETS:
        keys.update(classification.get(bucket, []))
    return keys


def build_target_microactions_payload(
    *,
    index: ScopeIndex,
    state_id: str,
    scope_state: dict[str, Any],
    classification: dict[str, Any],
    action_keys: set[str],
    prompt_profile: str = DEFAULT_PROMPT_PROFILE,
) -> list[dict[str, Any]]:
    by_key = {
        action["action_key"]: action
        for action in scope_state.get("active_root_micro_actions", [])
    }

    targets: list[dict[str, Any]] = []
    for action_key in sorted(action_keys):
        micro_action = by_key.get(action_key)
        if micro_action is None:
            raise KeyError(f"micro_action_id {action_key} not found in scope state {state_id}")

        yield_tier = find_yield_bucket(classification, action_key)
        if yield_tier is None:
            raise KeyError(f"micro_action_id {action_key} not found in yield_classification.json")

        if prompt_profile == "slim":
            entry: dict[str, Any] = {
                "micro_action_id": action_key,
                "yield": yield_tier,
                "task_count_guidance": TASK_COUNT_GUIDANCE[yield_tier],
                "name": micro_action.get("name"),
                "role": micro_action.get("role"),
            }
            if micro_action.get("is_enabled") is False:
                entry["is_enabled"] = False
            targets.append(entry)
            continue

        targets.append({
            "micro_action_id": action_key,
            "yield": yield_tier,
            "task_count_guidance": TASK_COUNT_GUIDANCE[yield_tier],
            "role": micro_action.get("role"),
            "name": micro_action.get("name"),
            "description": micro_action.get("description"),
            "bbox": micro_action.get("bbox"),
            "is_showing": micro_action.get("is_showing"),
            "is_enabled": micro_action.get("is_enabled"),
            "is_sensitive": micro_action.get("is_sensitive"),
            "reason": micro_action.get("reason"),
        })

    return targets


def build_prompt_replacements(
    *,
    index: ScopeIndex,
    state_id: str,
    scope_state: dict[str, Any],
    target_microactions: list[dict[str, Any]],
    action_keys: set[str],
    prompt_profile: str,
) -> dict[str, str]:
    if prompt_profile == "slim":
        slim_macro = index.build_slim_macro_context(state_id)
        active_root_line = index.build_slim_active_root_line(scope_state)
        if active_root_line:
            active_root_line = f"{active_root_line}\n"
        return {
            "macro_state_id": state_id,
            "macro_path_text": slim_macro["macro_path_text"],
            "active_root_line": active_root_line,
            "target_microactions_json": json.dumps(target_microactions, indent=2, ensure_ascii=False),
            "target_microaction_count": str(len(action_keys)),
        }

    macro_context = index.build_macro_context(state_id)
    active_root_context = index.build_active_root_context(scope_state)
    return {
        "macro_state_id": state_id,
        "macro_context_json": json.dumps(macro_context, indent=2, ensure_ascii=False),
        "active_root_context_json": json.dumps(active_root_context, indent=2, ensure_ascii=False),
        "target_microactions_json": json.dumps(target_microactions, indent=2, ensure_ascii=False),
        "target_microaction_ids_json": json.dumps(sorted(action_keys), indent=2),
        "target_microaction_count": str(len(action_keys)),
    }


def chunk_action_keys(action_keys: set[str], batch_size: int | None) -> list[set[str]]:
    sorted_keys = sorted(action_keys)
    if batch_size is None:
        return [set(sorted_keys)] if sorted_keys else []
    return [
        set(sorted_keys[index:index + batch_size])
        for index in range(0, len(sorted_keys), batch_size)
    ]


def parse_batch_size(value: str) -> int | None:
    if value == "all":
        return None
    try:
        batch_size = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be a positive integer or 'all'") from exc
    if batch_size < 1:
        raise argparse.ArgumentTypeError("batch size must be a positive integer or 'all'")
    return batch_size


def build_successful_microaction_record(action_id: str, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "micro_action_id": action_id,
        "task_type": output["task_type"],
        "task_count": len(output["task"]),
    }


def build_failed_microaction_records(action_keys: set[str], reason: str) -> list[dict[str, str]]:
    return [
        {
            "micro_action_id": action_id,
            "reason": reason,
        }
        for action_id in sorted(action_keys)
    ]


class BatchGenerationError(RuntimeError):
    def __init__(
        self,
        *,
        message: str,
        raw_response_path: Path | None = None,
        usage: dict[str, Any] | None = None,
        timings: dict[str, float] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response_path = raw_response_path
        self.usage = usage
        self.timings = timings


def generation_metadata(
    *,
    requested_action_keys: set[str],
    outputs: dict[str, dict[str, Any]],
    failed_microactions: list[dict[str, str]],
    batches: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    failed_ids = {
        item["micro_action_id"]
        for item in failed_microactions
        if isinstance(item.get("micro_action_id"), str)
    }
    return {
        "successful_microactions": [
            build_successful_microaction_record(action_id, output)
            for action_id, output in sorted(outputs.items())
        ],
        "failed_microactions": failed_microactions,
        "successful_micro_action_ids": sorted(outputs),
        "failed_micro_action_ids": sorted(failed_ids),
        "requested_micro_action_ids": sorted(requested_action_keys),
        "batches": batches,
        "status": status,
    }


def generate_tasks_batch(
    *,
    index: ScopeIndex,
    state_id: str,
    scope_state: dict[str, Any],
    action_keys: set[str],
    classification: dict[str, Any],
    openai_config: dict[str, str],
    run_dir: Path,
    completion_params: CompletionParams,
    dry_run: bool,
    batch_index: int,
    prompt_profile: str,
) -> dict[str, Any]:
    timer = StageTimer(log)

    with timer.stage("resolve_paths", macro_state_id=state_id):
        screenshot_path = index.resolve_screenshot_path(scope_state)

    with timer.stage("build_context", macro_state_id=state_id):
        target_microactions = build_target_microactions_payload(
            index=index,
            state_id=state_id,
            scope_state=scope_state,
            classification=classification,
            action_keys=action_keys,
            prompt_profile=prompt_profile,
        )

    with timer.stage("render_prompt", macro_state_id=state_id, microactions=len(action_keys)):
        prompt_text = render_prompt(
            load_prompt_template_for_profile(prompt_profile),
            build_prompt_replacements(
                index=index,
                state_id=state_id,
                scope_state=scope_state,
                target_microactions=target_microactions,
                action_keys=action_keys,
                prompt_profile=prompt_profile,
            ),
        )

    yield_counts: dict[str, int] = defaultdict(int)
    for target in target_microactions:
        yield_counts[str(target["yield"])] += 1
    yield_summary = ", ".join(f"{count} {tier}" for tier, count in sorted(yield_counts.items()))
    log.info(
        "Macro state %s batch=%d: prepared microactions=%d (%s) prompt_profile=%s prompt_chars=%d screenshot=%s",
        state_id,
        batch_index,
        len(action_keys),
        yield_summary,
        prompt_profile,
        len(prompt_text),
        screenshot_path,
    )
    for target in target_microactions:
        log.info(
            "  target %s yield=%s guidance=%s name=%r",
            target["micro_action_id"],
            target["yield"],
            target["task_count_guidance"],
            target.get("name"),
        )

    if dry_run:
        log.info("Macro state %s batch=%d: dry run, skipping API call", state_id, batch_index)
        return {
            "state_id": state_id,
            "batch_index": batch_index,
            "status": "dry_run",
            "generation_run": str(run_dir),
            "microaction_count": len(action_keys),
            "screenshot_path": screenshot_path,
            "prompt_profile": prompt_profile,
            "prompt_chars": len(prompt_text),
            "micro_action_ids": sorted(action_keys),
            "timings": timer.summary(),
        }

    with timer.stage("build_messages", macro_state_id=state_id):
        messages = build_openai_messages(prompt_text, screenshot_path)

    with timer.stage(
        "api_call",
        macro_state_id=state_id,
        microactions=len(action_keys),
    ):
        completion = openai_structured_completion(
            api_key=openai_config["api_key"],
            base_url=openai_config["base_url"],
            model=openai_config["model"],
            messages=messages,
            json_schema=MACROSTATE_TASKS_BATCH_SCHEMA,
            completion_params=completion_params,
        )

    raw_response_path = raw_batch_path(run_dir, batch_index)
    raw_response_path.parent.mkdir(parents=True, exist_ok=True)
    raw_response_path.write_text(
        json.dumps(completion.content, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    usage = {
        "num_tokens": completion.usage_cost.num_tokens,
        "cost": completion.usage_cost.cost_usd,
        "cost_source": completion.usage_cost.cost_source,
        "prompt_tokens": completion.usage_cost.prompt_tokens,
        "completion_tokens": completion.usage_cost.completion_tokens,
        "api_calls": 1,
    }

    try:
        with timer.stage("validate", macro_state_id=state_id):
            outputs = validate_macrostate_tasks_batch(completion.content, action_keys)
    except ValueError as exc:
        timings = timer.summary()
        timings["total"] = sum(timings.values())
        raise BatchGenerationError(
            message=str(exc),
            raw_response_path=raw_response_path,
            usage=usage,
            timings=timings,
        ) from exc

    formatted_outputs = {
        action_id: {
            "micro_action_id": action_id,
            "task_type": payload["task_type"],
            "task": payload["task"],
        }
        for action_id, payload in outputs.items()
    }
    total_tasks = sum(len(output["task"]) for output in formatted_outputs.values())
    log.info(
        "Macro state %s batch=%d: validated microactions=%d tasks=%d api_calls=1",
        state_id,
        batch_index,
        len(formatted_outputs),
        total_tasks,
    )
    for action_id, output in sorted(formatted_outputs.items()):
        log.info(
            "  microaction %s task_type=%s tasks=%d",
            action_id,
            output["task_type"],
            len(output["task"]),
        )

    timings = timer.summary()
    timings["total"] = sum(timings.values())

    log.info(
        "Macro state %s batch=%d: completed total_elapsed=%.2fs timings=%s",
        state_id,
        batch_index,
        timings["total"],
        json.dumps({key: round(value, 2) for key, value in timings.items()}),
    )

    return {
        "state_id": state_id,
        "batch_index": batch_index,
        "status": "generated",
        "generation_run": str(run_dir),
        "outputs": formatted_outputs,
        "usage": usage,
        "timings": timings,
        "api_calls": 1,
        "raw_response_path": str(raw_response_path),
        "micro_action_ids": sorted(action_keys),
    }


def empty_usage_totals() -> dict[str, Any]:
    return {
        "num_tokens": 0,
        "cost": 0.0,
        "cost_source": "mixed",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "api_calls": 0,
    }


def merge_usage_totals(total_usage: dict[str, Any], usage: dict[str, Any]) -> None:
    total_usage["num_tokens"] += usage["num_tokens"]
    total_usage["cost"] += usage["cost"]
    total_usage["prompt_tokens"] += usage["prompt_tokens"]
    total_usage["completion_tokens"] += usage["completion_tokens"]
    total_usage["api_calls"] += usage["api_calls"]


def build_run_settings_and_metadata(
    *,
    state_id: str,
    requested_action_keys: set[str],
    run_timestamp: str,
    openai_config: dict[str, str],
    creative: bool,
    completion_params: CompletionParams,
    all_outputs: dict[str, dict[str, Any]],
    failed_microactions: list[dict[str, str]],
    batch_results: list[dict[str, Any]],
    total_usage: dict[str, Any],
    timings: dict[str, float],
    run_dir: Path,
    batch_size: int | None,
    prompt_profile: str,
    status: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = generation_metadata(
        requested_action_keys=requested_action_keys,
        outputs=all_outputs,
        failed_microactions=failed_microactions,
        batches=batch_results,
        status=status,
    )
    metadata["timings_seconds"] = timings
    metadata["usage"] = total_usage
    metadata["api_calls"] = total_usage["api_calls"]
    metadata["macro_state_id"] = state_id
    metadata["model"] = openai_config["model"]
    metadata["generation_run"] = str(run_dir)
    metadata["batch_size"] = "all" if batch_size is None else batch_size
    metadata["prompt_profile"] = prompt_profile

    settings = build_settings_payload(
        timestamp=run_timestamp,
        macro_state_id=state_id,
        micro_action_ids=sorted(requested_action_keys),
        openai_config=openai_config,
        creative=creative,
        completion_params=completion_params.as_dict(),
        usage=total_usage,
        status=status,
    )
    settings["api_calls"] = total_usage["api_calls"]
    settings["timings_seconds"] = timings
    settings["batch_size"] = "all" if batch_size is None else batch_size
    settings["prompt_profile"] = prompt_profile
    return settings, metadata


def commit_run_checkpoint(
    *,
    state_id: str,
    requested_action_keys: set[str],
    run_timestamp: str,
    openai_config: dict[str, str],
    creative: bool,
    completion_params: CompletionParams,
    all_outputs: dict[str, dict[str, Any]],
    failed_microactions: list[dict[str, str]],
    batch_results: list[dict[str, Any]],
    total_usage: dict[str, Any],
    timings: dict[str, float],
    run_dir: Path,
    batch_size: int | None,
    prompt_profile: str,
    status: str,
    dry_run: bool,
    new_outputs: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    settings, metadata = build_run_settings_and_metadata(
        state_id=state_id,
        requested_action_keys=requested_action_keys,
        run_timestamp=run_timestamp,
        openai_config=openai_config,
        creative=creative,
        completion_params=completion_params,
        all_outputs=all_outputs,
        failed_microactions=failed_microactions,
        batch_results=batch_results,
        total_usage=total_usage,
        timings=timings,
        run_dir=run_dir,
        batch_size=batch_size,
        prompt_profile=prompt_profile,
        status=status,
    )
    if not dry_run:
        commit_generation_checkpoint(
            run_dir=run_dir,
            settings=settings,
            metadata=metadata,
            new_outputs=new_outputs,
        )
    return settings, metadata


def generate_tasks_for_macro_state(
    *,
    index: ScopeIndex,
    state_id: str,
    scope_state: dict[str, Any],
    action_keys: set[str],
    classification: dict[str, Any],
    openai_config: dict[str, str],
    workspace_root: Path,
    run_dir: Path,
    run_timestamp: str,
    creative: bool,
    completion_params: CompletionParams,
    dry_run: bool,
    batch_size: int | None,
    prompt_profile: str,
    resume: bool = False,
) -> dict[str, Any]:
    run_started = time.monotonic()
    if resume:
        run_state = load_generation_run_state(run_dir)
        all_outputs = dict(run_state["outputs"])
        failed_microactions = list(run_state["metadata"].get("failed_microactions", []))
        batch_results = list(run_state["batch_results"])
        total_usage = dict(run_state["metadata"].get("usage", empty_usage_totals()))
        run_timestamp = str(run_state["settings"].get("timestamp", run_timestamp))
        requested_action_keys = {
            item
            for item in run_state["metadata"].get("requested_micro_action_ids", [])
            if isinstance(item, str)
        }
        if not requested_action_keys:
            requested_action_keys = set(action_keys) | set(all_outputs)
        log.info(
            "Macro state %s: resuming generation run %s successes=%d batches=%d remaining=%d",
            state_id,
            run_dir,
            len(all_outputs),
            len(batch_results),
            len(action_keys),
        )
    else:
        all_outputs = {}
        failed_microactions = []
        batch_results = []
        total_usage = empty_usage_totals()
        requested_action_keys = set(action_keys)

    batches = chunk_action_keys(action_keys, batch_size)
    timings: dict[str, float] = {}
    batch_index_offset = len(batch_results)

    log.info(
        "Macro state %s: output_dir=%s microactions=%d batches=%d batch_size=%s prompt_profile=%s resume=%s",
        state_id,
        run_dir,
        len(action_keys),
        len(batches),
        "all" if batch_size is None else batch_size,
        prompt_profile,
        resume,
    )

    if not dry_run and not resume:
        timings["total"] = time.monotonic() - run_started
        commit_run_checkpoint(
            state_id=state_id,
            requested_action_keys=requested_action_keys,
            run_timestamp=run_timestamp,
            openai_config=openai_config,
            creative=creative,
            completion_params=completion_params,
            all_outputs=all_outputs,
            failed_microactions=failed_microactions,
            batch_results=batch_results,
            total_usage=total_usage,
            timings=timings,
            run_dir=run_dir,
            batch_size=batch_size,
            prompt_profile=prompt_profile,
            status=GENERATION_STATUS_IN_PROGRESS,
            dry_run=dry_run,
        )

    for batch_index, batch_action_keys in enumerate(batches, start=1):
        batch_number = batch_index_offset + batch_index
        batch_record: dict[str, Any] = {
            "batch_index": batch_number,
            "micro_action_ids": sorted(batch_action_keys),
            "status": "pending",
        }
        batch_started = time.monotonic()
        batch_new_outputs: dict[str, dict[str, Any]] = {}
        try:
            batch_result = generate_tasks_batch(
                index=index,
                state_id=state_id,
                scope_state=scope_state,
                action_keys=batch_action_keys,
                classification=classification,
                openai_config=openai_config,
                run_dir=run_dir,
                completion_params=completion_params,
                dry_run=dry_run,
                batch_index=batch_number,
                prompt_profile=prompt_profile,
            )
            batch_new_outputs = dict(batch_result.get("outputs", {}))
            batch_record.update({
                "status": batch_result["status"],
                "outputs": sorted(batch_new_outputs),
                "raw_response_path": batch_result.get("raw_response_path"),
                "usage": batch_result.get("usage"),
                "timings_seconds": batch_result.get("timings"),
            })
            all_outputs.update(batch_new_outputs)
            if batch_new_outputs:
                succeeded_ids = set(batch_new_outputs)
                failed_microactions = [
                    item
                    for item in failed_microactions
                    if item.get("micro_action_id") not in succeeded_ids
                ]
            if not dry_run:
                usage = batch_result["usage"]
                merge_usage_totals(total_usage, usage)
                log_task_generation_batch_cost(
                    workspace_root,
                    state_id,
                    openai_config["model"],
                    UsageCost(
                        num_tokens=usage["num_tokens"],
                        cost_usd=usage["cost"],
                        cost_source=usage["cost_source"],
                        prompt_tokens=usage["prompt_tokens"],
                        completion_tokens=usage["completion_tokens"],
                    ),
                    generation_run=str(run_dir),
                )
        except Exception as exc:
            reason = str(exc)
            log.exception(
                "Macro state %s batch=%d failed after %.2fs: %s",
                state_id,
                batch_number,
                time.monotonic() - batch_started,
                exc,
            )
            raw_response_path = (
                str(exc.raw_response_path)
                if isinstance(exc, BatchGenerationError) and exc.raw_response_path is not None
                else str(raw_batch_path(run_dir, batch_number))
            )
            batch_record.update({
                "status": "failed",
                "error": reason,
                "raw_response_path": raw_response_path,
            })
            if isinstance(exc, BatchGenerationError):
                if exc.usage is not None:
                    batch_record["usage"] = exc.usage
                    usage = exc.usage
                    if not dry_run:
                        merge_usage_totals(total_usage, usage)
                        log_task_generation_batch_cost(
                            workspace_root,
                            state_id,
                            openai_config["model"],
                            UsageCost(
                                num_tokens=usage["num_tokens"],
                                cost_usd=usage["cost"],
                                cost_source=usage["cost_source"],
                                prompt_tokens=usage["prompt_tokens"],
                                completion_tokens=usage["completion_tokens"],
                            ),
                            generation_run=str(run_dir),
                        )
                if exc.timings is not None:
                    batch_record["timings_seconds"] = exc.timings
            failed_microactions.extend(build_failed_microaction_records(batch_action_keys, reason))
        finally:
            batch_record["elapsed_seconds"] = time.monotonic() - batch_started
            batch_results.append(batch_record)
            timings["total"] = time.monotonic() - run_started
            if not dry_run:
                commit_run_checkpoint(
                    state_id=state_id,
                    requested_action_keys=requested_action_keys,
                    run_timestamp=run_timestamp,
                    openai_config=openai_config,
                    creative=creative,
                    completion_params=completion_params,
                    all_outputs=all_outputs,
                    failed_microactions=failed_microactions,
                    batch_results=batch_results,
                    total_usage=total_usage,
                    timings=timings,
                    run_dir=run_dir,
                    batch_size=batch_size,
                    prompt_profile=prompt_profile,
                    status=GENERATION_STATUS_IN_PROGRESS,
                    dry_run=dry_run,
                    new_outputs=batch_new_outputs or None,
                )

    if dry_run:
        status = "dry_run"
        total_usage["cost_source"] = "none"
    elif not failed_microactions:
        status = GENERATION_STATUS_GENERATED
    elif all_outputs:
        status = GENERATION_STATUS_PARTIAL
    else:
        status = GENERATION_STATUS_FAILED

    timings["total"] = time.monotonic() - run_started
    _, metadata = commit_run_checkpoint(
        state_id=state_id,
        requested_action_keys=requested_action_keys,
        run_timestamp=run_timestamp,
        openai_config=openai_config,
        creative=creative,
        completion_params=completion_params,
        all_outputs=all_outputs,
        failed_microactions=failed_microactions,
        batch_results=batch_results,
        total_usage=total_usage,
        timings=timings,
        run_dir=run_dir,
        batch_size=batch_size,
        prompt_profile=prompt_profile,
        status=status,
        dry_run=dry_run,
    )

    if dry_run:
        log.info(
            "Macro state %s: dry run complete status=%s batches=%d total_elapsed=%.2fs",
            state_id,
            status,
            len(batches),
            timings["total"],
        )
    else:
        log.info(
            "Macro state %s: wrote generation run to %s status=%s successes=%d failed=%d total_elapsed=%.2fs",
            state_id,
            run_dir,
            status,
            len(all_outputs),
            len(failed_microactions),
            timings["total"],
        )

    return {
        "state_id": state_id,
        "status": status,
        "generation_run": str(run_dir),
        "outputs": all_outputs,
        "metadata": metadata,
        "usage": total_usage,
        "timings": timings,
        "api_calls": total_usage["api_calls"],
        "batches": batch_results,
    }


def resolve_requested_actions(
    *,
    index: ScopeIndex,
    workspace_root: Path,
    classification_model: str,
    micro_action_ids: list[str],
    macro_state_ids: list[str],
) -> dict[str, set[str]]:
    by_state: dict[str, set[str]] = defaultdict(set)

    for micro_action_id in micro_action_ids:
        ref = index.get_micro_action_ref(micro_action_id)
        by_state[ref.state_id].add(micro_action_id)

    for state_id in macro_state_ids:
        classification = load_classification(
            workspace_root,
            state_id,
            classification_model=classification_model,
        )
        by_state[state_id].update(classified_action_keys(classification))

    return dict(by_state)


def filter_previously_successful_actions(
    *,
    requested_by_state: dict[str, set[str]],
    previous_generation_runs: list[Path],
) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    if not previous_generation_runs:
        return requested_by_state, {}

    successful_ids: set[str] = set()
    for run_dir in previous_generation_runs:
        successful_ids.update(successful_action_ids_from_generation_run(run_dir))

    filtered: dict[str, set[str]] = {}
    skipped: dict[str, list[str]] = {}
    for state_id, action_keys in requested_by_state.items():
        remaining = action_keys - successful_ids
        already_successful = sorted(action_keys & successful_ids)
        if remaining:
            filtered[state_id] = remaining
        if already_successful:
            skipped[state_id] = already_successful
    return filtered, skipped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-root",
        "--classification-root",
        dest="workspace_root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Synthetic workspace root containing classification/ and task_generation/ directories.",
    )
    parser.add_argument(
        "--classification-model",
        default=None,
        help="Model directory under classification/ to read yield classifications from.",
    )
    parser.add_argument(
        "--micro-action-id",
        action="append",
        default=[],
        help="Microaction id (action_key) to generate tasks for (repeatable).",
    )
    parser.add_argument(
        "--macro-state-id",
        action="append",
        default=[],
        help="Generate tasks for all classified microactions in this macro state (repeatable).",
    )
    parser.add_argument(
        "--previous-generation-run",
        "--previous-generation-runs",
        action="append",
        type=Path,
        default=[],
        help=(
            "Existing generation run folder with metadata.json. Repeatable. "
            "Microactions successful in any provided run are skipped."
        ),
    )
    parser.add_argument(
        "--resume-generation-run",
        type=Path,
        default=None,
        help=(
            "Resume an in_progress generation run folder. "
            "Validated batches already committed in that run are preserved."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=parse_batch_size,
        default=DEFAULT_BATCH_SIZE,
        help=(
            f"Number of microactions per strict generation batch (default: {DEFAULT_BATCH_SIZE}). "
            "Use 'all' to request all pending microactions in one batch."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--prompt-profile",
        choices=PROMPT_PROFILES,
        default=DEFAULT_PROMPT_PROFILE,
        help=(
            "Prompt template and context verbosity "
            f"(default: {DEFAULT_PROMPT_PROFILE}). "
            "'slim' omits agent_map/toolbar inventories and uses a compact task-type list."
        ),
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    parser.add_argument("--model", default=None)
    add_completion_args(parser)
    parser.add_argument("--env-file", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(verbose=args.verbose)
    run_started = time.monotonic()

    if not args.micro_action_id and not args.macro_state_id:
        print(json.dumps({
            "ok": False,
            "error": "provide --micro-action-id and/or --macro-state-id",
        }, indent=2), file=sys.stderr)
        return 2

    root = repo_root()
    workspace_root = resolve_repo_path(args.workspace_root)
    try:
        classification_model = resolve_classification_model(
            workspace_root,
            args.classification_model,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    env_path = args.env_file or (root / ".env")

    index = ScopeIndex.load(repo_root=root)

    load_env_file(env_path)
    completion_params = completion_params_from_args(args)
    if completion_params.max_tokens is None:
        completion_params = completion_params.merge(CompletionParams(max_tokens=DEFAULT_MAX_TOKENS))
    log.info(
        "stage=startup status=done workspace_root=%s classification_model=%s dry_run=%s creative=%s batch_size=%s prompt_profile=%s",
        workspace_root,
        classification_model,
        args.dry_run,
        args.creative,
        "all" if args.batch_size is None else args.batch_size,
        args.prompt_profile,
    )
    if completion_params.as_dict():
        log.info("Completion params: %s", completion_params.as_dict())
    elif args.creative:
        log.info("Using --creative preset with no explicit overrides")

    if args.dry_run:
        openai_config = {
            "api_key": "",
            "base_url": "",
            "model": args.model or "",
        }
    else:
        try:
            openai_config = resolve_openai_config(env_path=env_path, model_override=args.model)
        except RuntimeError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
            return 2
        log.info("Using model=%s base_url=%s", openai_config["model"], openai_config["base_url"])

    try:
        requested_by_state = resolve_requested_actions(
            index=index,
            workspace_root=workspace_root,
            classification_model=classification_model,
            micro_action_ids=args.micro_action_id,
            macro_state_ids=args.macro_state_id,
        )
    except (KeyError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    previous_runs = [resolve_repo_path(path) for path in args.previous_generation_run]
    resume_run = resolve_repo_path(args.resume_generation_run) if args.resume_generation_run else None
    if resume_run is not None and not resume_run.exists():
        print(json.dumps({
            "ok": False,
            "error": f"resume generation run not found: {resume_run}",
        }, indent=2), file=sys.stderr)
        return 1

    skip_runs = list(previous_runs)
    if resume_run is not None:
        skip_runs.append(resume_run)
    try:
        requested_by_state, skipped_successful = filter_previously_successful_actions(
            requested_by_state=requested_by_state,
            previous_generation_runs=skip_runs,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    total_microactions = sum(len(keys) for keys in requested_by_state.values())
    log.info(
        "Resolved macro_states=%d microactions=%d batch_size=%s",
        len(requested_by_state),
        total_microactions,
        "all" if args.batch_size is None else args.batch_size,
    )
    if skipped_successful:
        skipped_count = sum(len(ids) for ids in skipped_successful.values())
        log.info(
            "Skipped %d microaction(s) already successful in previous generation run(s)",
            skipped_count,
        )

    processed: list[str] = []
    failed: list[dict[str, str]] = []
    batch_results: list[dict[str, Any]] = []

    for state_id in sorted(requested_by_state):
        action_keys = requested_by_state[state_id]
        pending: set[str] = set()
        state_started = time.monotonic()
        log.info("stage=macro_state status=start macro_state_id=%s microactions=%d", state_id, len(action_keys))
        try:
            scope_state = index.get_scope_state(state_id)
            classification = load_classification(
                workspace_root,
                state_id,
                classification_model=classification_model,
            )

            for action_key in sorted(action_keys):
                if find_yield_bucket(classification, action_key) is None:
                    log.error(
                        "Microaction %s missing from yield_classification.json for state %s",
                        action_key,
                        state_id,
                    )
                    failed.append({
                        "micro_action_id": action_key,
                        "error": f"not found in yield_classification.json for state {state_id}",
                    })
                    continue
                pending.add(action_key)

            if not pending:
                continue

            resume = False
            run_timestamp = utc_run_timestamp()
            if (
                resume_run is not None
                and resume_run.parent.parent.parent.name == state_id
            ):
                if not is_in_progress_generation_run(resume_run):
                    raise RuntimeError(
                        f"cannot resume finalized generation run: {resume_run}"
                    )
                run_dir = resume_run
                resume = True
                log.info(
                    "Macro state %s: resuming output_dir=%s microactions=%d",
                    state_id,
                    run_dir,
                    len(pending),
                )
            else:
                run_dir = generation_run_dir(
                    workspace_root,
                    state_id,
                    model=openai_config["model"],
                    timestamp=run_timestamp,
                )
                log.info(
                    "Macro state %s: output_dir=%s microactions=%d",
                    state_id,
                    run_dir,
                    len(pending),
                )

            result = generate_tasks_for_macro_state(
                index=index,
                state_id=state_id,
                scope_state=scope_state,
                action_keys=pending,
                classification=classification,
                openai_config=openai_config,
                workspace_root=workspace_root,
                run_dir=run_dir,
                run_timestamp=run_timestamp,
                creative=args.creative,
                completion_params=completion_params,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                prompt_profile=args.prompt_profile,
                resume=resume,
            )
            batch_results.append(result)

            if not args.dry_run:
                processed.extend(sorted(result["outputs"]))
                for item in result.get("metadata", {}).get("failed_microactions", []):
                    action_id = item.get("micro_action_id")
                    reason = item.get("reason", "generation failed")
                    if isinstance(action_id, str):
                        failed.append({"micro_action_id": action_id, "error": str(reason)})
            else:
                processed.extend(sorted(pending))
            log.info(
                "stage=macro_state status=%s macro_state_id=%s elapsed=%.2fs",
                result["status"],
                state_id,
                time.monotonic() - state_started,
            )
        except Exception as exc:
            log.exception("Macro state %s failed after %.2fs: %s", state_id, time.monotonic() - state_started, exc)
            for action_key in sorted(pending or action_keys):
                failed.append({
                    "micro_action_id": action_key,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })

    log.info(
        "stage=run status=done elapsed=%.2fs processed=%d failed=%d",
        time.monotonic() - run_started,
        len(processed),
        len(failed),
    )

    print(json.dumps({
        "ok": len(failed) == 0,
        "action": "dry_run" if args.dry_run else "generate_tasks",
        "workspace_root": str(workspace_root),
        "classification_model": classification_model,
        "processed": processed,
        "failed": [{"micro_action_id": item["micro_action_id"], "error": item["error"]} for item in failed],
        "skipped_successful": skipped_successful,
        "batches": batch_results,
        "model": openai_config.get("model"),
        "creative": args.creative,
        "prompt_profile": args.prompt_profile,
        "completion_params": completion_params.as_dict(),
        "elapsed_seconds": time.monotonic() - run_started,
    }, indent=2))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
