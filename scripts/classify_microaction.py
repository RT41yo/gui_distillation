#!/usr/bin/env python3
"""Classify microactions by yield tier for each macro state."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.cost_log import log_classification_cost
from ui_explorer.synthetic.env import load_env_file, resolve_openai_config
from ui_explorer.synthetic.io import load_json, save_json
from ui_explorer.synthetic.llm_args import CompletionParams, add_completion_args, completion_params_from_args
from ui_explorer.synthetic.logging_config import configure_logging
from ui_explorer.synthetic.openai_client import build_openai_messages, openai_structured_completion
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, repo_root, resolve_repo_path
from ui_explorer.synthetic.schemas import (
    YIELD_CLASSIFICATION_SCHEMA,
    YIELD_GUIDANCE,
    validate_yield_classification,
)
from ui_explorer.synthetic.scope_index import ScopeIndex, load_prompt_template, render_prompt
from ui_explorer.synthetic.timing import StageTimer

log = logging.getLogger(__name__)


def classify_state(
    *,
    index: ScopeIndex,
    state_id: str,
    scope_state: dict[str, Any],
    openai_config: dict[str, str],
    output_root: Path,
    completion_params: CompletionParams,
    dry_run: bool,
) -> dict[str, Any]:
    timer = StageTimer(log)
    expected_keys = index.expected_action_keys(scope_state)

    with timer.stage("build_context", macro_state_id=state_id):
        macro_context = index.build_macro_context(state_id)
        active_root_context = index.build_active_root_context(scope_state)
        microactions = index.microactions_for_prompt(scope_state)
        screenshot_path = index.resolve_screenshot_path(scope_state)

    with timer.stage("render_prompt", macro_state_id=state_id, microactions=len(expected_keys)):
        prompt_text = render_prompt(
            load_prompt_template("classify_microactions.md"),
            {
                "macro_state_id": state_id,
                "macro_context_json": json.dumps(macro_context, indent=2, ensure_ascii=False),
                "active_root_context_json": json.dumps(active_root_context, indent=2, ensure_ascii=False),
                "microactions_json": json.dumps(microactions, indent=2, ensure_ascii=False),
                "yield_guidance_json": json.dumps(YIELD_GUIDANCE, indent=2, ensure_ascii=False),
            },
        )

    log.info(
        "Macro state %s: classify batch prepared microactions=%d prompt_chars=%d api_calls=1",
        state_id,
        len(expected_keys),
        len(prompt_text),
    )

    if dry_run:
        return {
            "state_id": state_id,
            "status": "dry_run",
            "microaction_count": len(expected_keys),
            "screenshot_path": screenshot_path,
            "prompt_chars": len(prompt_text),
            "timings": timer.summary(),
        }

    with timer.stage("build_messages", macro_state_id=state_id):
        messages = build_openai_messages(prompt_text, screenshot_path)

    with timer.stage("api_call", macro_state_id=state_id, microactions=len(expected_keys)):
        completion = openai_structured_completion(
            api_key=openai_config["api_key"],
            base_url=openai_config["base_url"],
            model=openai_config["model"],
            messages=messages,
            json_schema=YIELD_CLASSIFICATION_SCHEMA,
            completion_params=completion_params,
        )

    with timer.stage("validate", macro_state_id=state_id):
        validate_yield_classification(completion.content, expected_keys)

    with timer.stage("log_cost", macro_state_id=state_id):
        log_classification_cost(output_root, state_id, completion.model, completion.usage_cost)

    timings = timer.summary()
    timings["total"] = sum(timings.values())
    log.info(
        "Macro state %s: classified microactions=%d total_elapsed=%.2fs timings=%s",
        state_id,
        len(expected_keys),
        timings["total"],
        json.dumps({key: round(value, 2) for key, value in timings.items()}),
    )

    return {
        "state_id": state_id,
        "status": "classified",
        "classification": completion.content,
        "usage": {
            "num_tokens": completion.usage_cost.num_tokens,
            "cost": completion.usage_cost.cost_usd,
            "cost_source": completion.usage_cost.cost_source,
        },
        "timings": timings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root output directory for per-state yield_classification.json files.",
    )
    parser.add_argument(
        "--macro-state-id",
        action="append",
        default=[],
        help="Macro state id to classify (repeatable). Default: all states with microactions.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    parser.add_argument("--model", default=None)
    add_completion_args(parser)
    parser.add_argument("--env-file", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(verbose=args.verbose)
    run_started = time.monotonic()

    root = repo_root()
    output_root = resolve_repo_path(args.output_root)
    env_path = args.env_file or (root / ".env")

    index = ScopeIndex.load(repo_root=root)
    states = index.states_with_microactions()

    if args.macro_state_id:
        wanted = set(args.macro_state_id)
        states = [(sid, st) for sid, st in states if sid in wanted]
        missing = wanted - {sid for sid, _ in states}
        if missing:
            print(json.dumps({
                "ok": False,
                "error": "unknown macro state ids",
                "missing": sorted(missing),
            }, indent=2), file=sys.stderr)
            return 1

    if args.limit is not None:
        states = states[: args.limit]

    if not states:
        print(json.dumps({"ok": False, "error": "no macro states matched selection"}, indent=2))
        return 1

    load_env_file(env_path)
    completion_params = completion_params_from_args(args)
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

    processed: list[str] = []
    skipped: list[str] = []
    failed: list[dict[str, str]] = []

    for state_id, scope_state in states:
        out_dir = output_root / state_id
        out_path = out_dir / "yield_classification.json"

        if out_path.exists() and not args.overwrite:
            skipped.append(state_id)
            continue

        state_started = time.monotonic()
        log.info("stage=macro_state status=start macro_state_id=%s", state_id)
        try:
            result = classify_state(
                index=index,
                state_id=state_id,
                scope_state=scope_state,
                openai_config=openai_config,
                output_root=output_root,
                completion_params=completion_params,
                dry_run=args.dry_run,
            )
            if not args.dry_run:
                save_json(out_path, result["classification"])
            processed.append(state_id)
            log.info(
                "stage=macro_state status=done macro_state_id=%s elapsed=%.2fs",
                state_id,
                time.monotonic() - state_started,
            )
        except Exception as exc:
            log.exception(
                "Macro state %s failed after %.2fs: %s",
                state_id,
                time.monotonic() - state_started,
                exc,
            )
            failed.append({
                "state_id": state_id,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })

    log.info(
        "stage=run status=done elapsed=%.2fs processed=%d skipped=%d failed=%d",
        time.monotonic() - run_started,
        len(processed),
        len(skipped),
        len(failed),
    )

    print(json.dumps({
        "ok": len(failed) == 0,
        "action": "dry_run" if args.dry_run else "classify",
        "output_root": str(output_root),
        "state_count": len(states),
        "processed": processed,
        "skipped": skipped,
        "failed": [{"state_id": item["state_id"], "error": item["error"]} for item in failed],
        "model": openai_config.get("model"),
        "completion_params": completion_params.as_dict(),
        "elapsed_seconds": time.monotonic() - run_started,
    }, indent=2))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
