#!/usr/bin/env python3
"""Live per-macro-state progress bars for task generation (microactions + batches)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ui_explorer.synthetic.generation_output import (
    in_flight_generation_progress,
    list_classified_state_ids,
    resolve_classification_model,
)
from ui_explorer.synthetic.generation_progress import (
    format_macro_state_bar_line,
    format_progress_bar,
    macro_state_progress_counts,
    resolve_row_status,
    snapshot_macro_state,
    status_sort_key,
)
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, resolve_repo_path

REFRESH_INTERVAL_SECONDS = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-root",
        "--classification-root",
        dest="workspace_root",
        type=Path,
        default=resolve_repo_path(DEFAULT_OUTPUT_ROOT),
    )
    parser.add_argument(
        "--classification-model",
        default=None,
        help="Model directory under classification/ to read yield classifications from.",
    )
    parser.add_argument(
        "--macro-state-id",
        action="append",
        default=[],
        help="Macro state to watch (repeatable). Default: all classified macro states.",
    )
    parser.add_argument("--model", required=True, help="Generation model directory to watch.")
    parser.add_argument(
        "--bar-width",
        type=int,
        default=24,
        help="Character width of each macro-state progress bar (default: 24).",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=REFRESH_INTERVAL_SECONDS,
        help=f"Refresh interval in seconds (default: {REFRESH_INTERVAL_SECONDS}).",
    )
    parser.add_argument(
        "--progress-path",
        type=Path,
        default=None,
        help="Optional file to mirror the live display (for tail -f).",
    )
    return parser.parse_args()


def resolve_state_ids(
    *,
    workspace_root: Path,
    classification_model: str,
    macro_state_ids: list[str],
) -> list[str]:
    if macro_state_ids:
        return sorted(macro_state_ids)
    return list_classified_state_ids(
        workspace_root,
        classification_model=classification_model,
    )


def collect_rows(
    *,
    workspace_root: Path,
    state_ids: list[str],
    model: str,
    classification_model: str,
) -> list[tuple[str, object, int, int, int, int | None]]:
    rows: list[tuple[str, object, int, int, int, int | None]] = []
    for state_id in state_ids:
        in_flight = in_flight_generation_progress(
            workspace_root=workspace_root,
            state_id=state_id,
            model=model,
        )
        snapshot = snapshot_macro_state(
            workspace_root=workspace_root,
            state_id=state_id,
            model=model,
            classification_model=classification_model,
        )
        status = resolve_row_status(snapshot, in_flight=in_flight)
        micro_done, micro_total, batches_done, batches_total = macro_state_progress_counts(snapshot)
        rows.append((status, snapshot, micro_done, micro_total, batches_done, batches_total))
    rows.sort(key=lambda item: (status_sort_key(item[0]), item[1].state_id))
    return rows


def build_display_lines(
    *,
    model: str,
    rows: list[tuple[str, object, int, int, int, int | None]],
    elapsed_seconds: float,
    bar_width: int,
) -> list[str]:
    total_expected = sum(item[3] for item in rows)
    total_done = sum(min(item[2], item[3]) if item[3] else item[2] for item in rows)
    complete_states = sum(1 for status, *_ in rows if status == "complete")
    running_states = sum(1 for status, *_ in rows if status == "running")

    summary_bar = format_progress_bar(total_done, total_expected, width=bar_width)
    lines = [
        (
            f"Task generation watch  model={model}  "
            f"states={complete_states}/{len(rows)} running={running_states}  "
            f"microactions={total_done}/{total_expected}  "
            f"elapsed={elapsed_seconds:,.0f}s"
        ),
        f"Overall  {summary_bar}  {total_done}/{total_expected}",
        "",
        f"{'Macro state':<14} {'Microactions':<{bar_width + 10}} {'Batch':<{max(8, bar_width // 2) + 12}} Status",
        "-" * (14 + bar_width + 10 + max(8, bar_width // 2) + 12 + 8),
    ]
    for status, snapshot, *_ in rows:
        lines.append(
            format_macro_state_bar_line(snapshot, width=bar_width, status=status)
        )
    return lines


def render_loop(
    *,
    stream,
    lines: list[str],
    rendered_lines: int,
) -> int:
    if stream.isatty():
        if rendered_lines > 0:
            stream.write(f"\033[{rendered_lines}F")
        for line in lines:
            stream.write(f"\033[2K{line}\n")
        stream.flush()
        return len(lines)

    print("\n".join(lines), flush=True)
    return 0


def main() -> int:
    args = parse_args()
    workspace_root = args.workspace_root.resolve()
    try:
        classification_model = resolve_classification_model(
            workspace_root,
            args.classification_model,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    state_ids = resolve_state_ids(
        workspace_root=workspace_root,
        classification_model=classification_model,
        macro_state_ids=args.macro_state_id,
    )
    if not state_ids:
        print("No classified macro states found to watch.", file=sys.stderr)
        return 2

    started = time.monotonic()
    rendered_lines = 0
    stream = sys.stderr if sys.stderr.isatty() else sys.stdout

    try:
        while True:
            rows = collect_rows(
                workspace_root=workspace_root,
                state_ids=state_ids,
                model=args.model,
                classification_model=classification_model,
            )
            lines = build_display_lines(
                model=args.model,
                rows=rows,
                elapsed_seconds=time.monotonic() - started,
                bar_width=args.bar_width,
            )
            text = "\n".join(lines) + "\n"

            rendered_lines = render_loop(
                stream=stream,
                lines=lines,
                rendered_lines=rendered_lines,
            )

            if args.progress_path is not None:
                args.progress_path.parent.mkdir(parents=True, exist_ok=True)
                args.progress_path.write_text(text, encoding="utf-8")

            time.sleep(args.refresh)
    except KeyboardInterrupt:
        if stream.isatty() and rendered_lines > 0:
            stream.write("\n")
            stream.flush()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
