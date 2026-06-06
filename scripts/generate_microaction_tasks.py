#!/usr/bin/env python3
"""Generate task instructions for classified microactions (batched per macro state)."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.cost_log import log_task_generation_batch_cost
from ui_explorer.synthetic.env import load_env_file, resolve_openai_config
from ui_explorer.synthetic.io import load_json, save_json
from ui_explorer.synthetic.openai_client import build_openai_messages, openai_structured_completion
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, repo_root, resolve_repo_path
from ui_explorer.synthetic.schemas import (
    MACROSTATE_TASKS_BATCH_SCHEMA,
    TASK_COUNT_GUIDANCE,
    YIELD_BUCKETS,
    find_yield_bucket,
    validate_macrostate_tasks_batch,
)
from ui_explorer.synthetic.scope_index import ScopeIndex, load_prompt_template, render_prompt


def load_classification(classification_root: Path, state_id: str) -> dict[str, Any]:
    path = classification_root / state_id / "yield_classification.json"
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


def generate_tasks_for_macro_state(
    *,
    index: ScopeIndex,
    state_id: str,
    scope_state: dict[str, Any],
    action_keys: set[str],
    classification: dict[str, Any],
    openai_config: dict[str, str],
    output_root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    macro_context = index.build_macro_context(state_id)
    active_root_context = index.build_active_root_context(scope_state)
    screenshot_path = index.resolve_screenshot_path(scope_state)
    target_microactions = build_target_microactions_payload(
        index=index,
        state_id=state_id,
        scope_state=scope_state,
        classification=classification,
        action_keys=action_keys,
    )

    prompt_text = render_prompt(
        load_prompt_template("generate_tasks.md"),
        {
            "macro_state_id": state_id,
            "macro_context_json": json.dumps(macro_context, indent=2, ensure_ascii=False),
            "active_root_context_json": json.dumps(active_root_context, indent=2, ensure_ascii=False),
            "target_microactions_json": json.dumps(target_microactions, indent=2, ensure_ascii=False),
        },
    )

    if dry_run:
        return {
            "state_id": state_id,
            "status": "dry_run",
            "microaction_count": len(action_keys),
            "screenshot_path": screenshot_path,
            "prompt_chars": len(prompt_text),
            "micro_action_ids": sorted(action_keys),
        }

    messages = build_openai_messages(prompt_text, screenshot_path)
    completion = openai_structured_completion(
        api_key=openai_config["api_key"],
        base_url=openai_config["base_url"],
        model=openai_config["model"],
        messages=messages,
        json_schema=MACROSTATE_TASKS_BATCH_SCHEMA,
    )

    outputs = validate_macrostate_tasks_batch(completion.content, action_keys)
    log_task_generation_batch_cost(output_root, state_id, completion.model, completion.usage_cost)

    return {
        "state_id": state_id,
        "status": "generated",
        "outputs": {
            action_id: {"micro_action_id": action_id, "task": tasks}
            for action_id, tasks in outputs.items()
        },
        "usage": {
            "num_tokens": completion.usage_cost.num_tokens,
            "cost": completion.usage_cost.cost_usd,
            "cost_source": completion.usage_cost.cost_source,
        },
    }


def resolve_requested_actions(
    *,
    index: ScopeIndex,
    classification_root: Path,
    micro_action_ids: list[str],
    macro_state_ids: list[str],
) -> dict[str, set[str]]:
    by_state: dict[str, set[str]] = defaultdict(set)

    for micro_action_id in micro_action_ids:
        ref = index.get_micro_action_ref(micro_action_id)
        by_state[ref.state_id].add(micro_action_id)

    for state_id in macro_state_ids:
        classification = load_classification(classification_root, state_id)
        by_state[state_id].update(classified_action_keys(classification))

    return dict(by_state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classification-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory containing {state_id}/yield_classification.json files.",
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
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.micro_action_id and not args.macro_state_id:
        print(json.dumps({
            "ok": False,
            "error": "provide --micro-action-id and/or --macro-state-id",
        }, indent=2), file=sys.stderr)
        return 2

    root = repo_root()
    classification_root = resolve_repo_path(args.classification_root)
    env_path = args.env_file or (root / ".env")

    index = ScopeIndex.load(repo_root=root)

    load_env_file(env_path)
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

    try:
        requested_by_state = resolve_requested_actions(
            index=index,
            classification_root=classification_root,
            micro_action_ids=args.micro_action_id,
            macro_state_ids=args.macro_state_id,
        )
    except (KeyError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    processed: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []
    batch_results: list[dict[str, Any]] = []

    for state_id in sorted(requested_by_state):
        action_keys = requested_by_state[state_id]
        try:
            scope_state = index.get_scope_state(state_id)
            classification = load_classification(classification_root, state_id)

            pending = set()
            for action_key in sorted(action_keys):
                out_path = classification_root / state_id / f"{action_key}.json"
                if out_path.exists() and not args.overwrite:
                    skipped.append(action_key)
                    continue
                if find_yield_bucket(classification, action_key) is None:
                    failed.append({
                        "micro_action_id": action_key,
                        "error": f"not found in yield_classification.json for state {state_id}",
                    })
                    continue
                pending.add(action_key)

            if not pending:
                continue

            result = generate_tasks_for_macro_state(
                index=index,
                state_id=state_id,
                scope_state=scope_state,
                action_keys=pending,
                classification=classification,
                openai_config=openai_config,
                output_root=classification_root,
                dry_run=args.dry_run,
            )
            batch_results.append(result)

            if not args.dry_run:
                for action_key, output in result["outputs"].items():
                    save_json(classification_root / state_id / f"{action_key}.json", output)
                    processed.append(action_key)
            else:
                processed.extend(sorted(pending))
        except Exception as exc:
            for action_key in action_keys:
                failed.append({
                    "micro_action_id": action_key,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })

    print(json.dumps({
        "ok": len(failed) == 0,
        "action": "dry_run" if args.dry_run else "generate_tasks",
        "classification_root": str(classification_root),
        "processed": processed,
        "skipped": skipped,
        "failed": [{"micro_action_id": item["micro_action_id"], "error": item["error"]} for item in failed],
        "batches": batch_results,
        "model": openai_config.get("model"),
    }, indent=2))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
