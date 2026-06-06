#!/usr/bin/env python3
"""Poll on-disk generation progress without touching a running retry process."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ui_explorer.synthetic.generation_progress import (
    format_progress_lines,
    snapshot_macro_state,
)
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, resolve_repo_path

REFRESH_INTERVAL_SECONDS = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classification-root",
        type=Path,
        default=resolve_repo_path(DEFAULT_OUTPUT_ROOT),
    )
    parser.add_argument("--macro-state-id", action="append", default=[])
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--progress-path",
        type=Path,
        default=None,
        help="Optional file to mirror the live table (for tail -f).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.macro_state_id:
        print("Provide at least one --macro-state-id", file=sys.stderr)
        return 2

    classification_root = args.classification_root.resolve()
    started = time.monotonic()
    rendered_lines = 0
    stream = sys.stderr if sys.stderr.isatty() else sys.stdout

    try:
        while True:
            rows = [
                snapshot_macro_state(
                    classification_root=classification_root,
                    state_id=state_id,
                    model=args.model,
                    status="running",
                )
                for state_id in args.macro_state_id
            ]
            lines = format_progress_lines(
                model=args.model,
                rows=rows,
                elapsed_seconds=time.monotonic() - started,
                active_state_id=args.macro_state_id[0] if len(args.macro_state_id) == 1 else None,
            )
            text = "\n".join(lines) + "\n"

            if stream.isatty():
                if rendered_lines > 0:
                    stream.write(f"\033[{rendered_lines}F")
                for line in lines:
                    stream.write(f"\033[2K{line}\n")
                rendered_lines = len(lines)
                stream.flush()
            else:
                print(text, end="")

            if args.progress_path is not None:
                args.progress_path.parent.mkdir(parents=True, exist_ok=True)
                args.progress_path.write_text(text, encoding="utf-8")

            time.sleep(REFRESH_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        if stream.isatty() and rendered_lines > 0:
            stream.write("\n")
            stream.flush()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
