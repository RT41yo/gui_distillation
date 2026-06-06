#!/usr/bin/env python3
"""Retry microaction task generation until every classified microaction succeeds."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from ui_explorer.synthetic.env import resolve_openai_config
from ui_explorer.synthetic.generation_output import (
    classification_path,
    find_resumable_generation_run,
    generation_coverage,
    list_generation_runs,
    model_dir_name,
    resolve_classification_model,
    utc_run_timestamp,
)
from ui_explorer.synthetic.generation_progress import (
    format_progress_lines,
    snapshot_macro_state,
)
from ui_explorer.synthetic.logging_config import configure_file_logging
from ui_explorer.synthetic.paths import DEFAULT_OUTPUT_ROOT, LOGS_DIRNAME, repo_root, resolve_repo_path
from ui_explorer.synthetic.scope_index import ScopeIndex

log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZES = (6, 2, 1)
GENERATE_SCRIPT = Path(__file__).resolve().parent / "generate_microaction_tasks.py"
PROGRESS_FILENAME = "progress.txt"
REFRESH_INTERVAL_SECONDS = 0.5


def resolve_display_stream() -> TextIO | None:
    if sys.stderr.isatty():
        return sys.stderr
    if sys.stdout.isatty():
        return sys.stdout
    return None


@dataclass
class ProgressBoard:
    workspace_root: Path
    model: str
    classification_model: str
    state_ids: list[str]
    started: float = field(default_factory=time.monotonic)
    active_state_id: str | None = None
    attempt_label: str = ""
    row_status: dict[str, str] = field(default_factory=dict)
    row_notes: dict[str, str] = field(default_factory=dict)
    progress_path: Path | None = None
    _stream: TextIO | None = field(default=None)
    _rendered_lines: int = 0

    def __post_init__(self) -> None:
        if self._stream is None:
            self._stream = resolve_display_stream()
        for state_id in self.state_ids:
            self.row_status[state_id] = "pending"
            self.row_notes[state_id] = ""
        self.render()

    def set_active(self, state_id: str | None, *, attempt_label: str = "") -> None:
        self.active_state_id = state_id
        self.attempt_label = attempt_label
        if state_id is not None:
            self.row_status[state_id] = "running"
            self.row_notes[state_id] = attempt_label

    def mark_result(self, state_id: str, status: str, *, note: str = "") -> None:
        self.row_status[state_id] = status
        self.row_notes[state_id] = note

    def _build_lines(self) -> list[str]:
        rows = []
        for state_id in self.state_ids:
            status = self.row_status.get(state_id, "pending")
            note = self.row_notes.get(state_id, "")
            attempt_label = self.attempt_label if state_id == self.active_state_id else ""
            rows.append(
                snapshot_macro_state(
                    workspace_root=self.workspace_root,
                    state_id=state_id,
                    model=self.model,
                    classification_model=self.classification_model,
                    status=status,
                    note=note,
                    attempt_label=attempt_label,
                )
            )
        return format_progress_lines(
            model=self.model,
            rows=rows,
            elapsed_seconds=time.monotonic() - self.started,
            active_state_id=self.active_state_id,
            attempt_label=self.attempt_label,
        )

    def render(self) -> None:
        lines = self._build_lines()
        text = "\n".join(lines) + "\n"

        if self.progress_path is not None:
            self.progress_path.parent.mkdir(parents=True, exist_ok=True)
            self.progress_path.write_text(text, encoding="utf-8")

        if self._stream is not None and self._stream.isatty():
            if self._rendered_lines > 0:
                self._stream.write(f"\033[{self._rendered_lines}F")
            for line in lines:
                self._stream.write(f"\033[2K{line}\n")
            self._rendered_lines = len(lines)
            self._stream.flush()

    def finalize(self) -> None:
        if self._stream is not None and self._stream.isatty() and self._rendered_lines > 0:
            self._stream.write("\n")
            self._stream.flush()
            self._rendered_lines = 0


def parse_batch_sizes(value: str) -> tuple[int, ...]:
    sizes: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        size = int(part)
        if size < 1:
            raise argparse.ArgumentTypeError("batch sizes must be positive integers")
        sizes.append(size)
    if not sizes:
        raise argparse.ArgumentTypeError("provide at least one batch size")
    return tuple(sizes)


def batch_size_for_attempt(batch_sizes: tuple[int, ...], attempt: int) -> int:
    index = min(attempt - 1, len(batch_sizes) - 1)
    return batch_sizes[index]


def run_log_path(workspace_root: Path, run_timestamp: str) -> Path:
    return workspace_root / LOGS_DIRNAME / run_timestamp / "run.log"


def build_generation_command(
    *,
    workspace_root: Path,
    classification_model: str,
    state_id: str,
    previous_runs: list[Path],
    resume_run: Path | None,
    batch_size: int,
    prompt_profile: str,
    model: str,
    env_file: Path | None,
    extra_args: list[str],
) -> list[str]:
    cmd = [
        sys.executable,
        str(GENERATE_SCRIPT),
        "--workspace-root",
        str(workspace_root),
        "--classification-model",
        classification_model,
        "--macro-state-id",
        state_id,
        "--batch-size",
        str(batch_size),
        "--prompt-profile",
        prompt_profile,
        "--model",
        model,
    ]
    if env_file is not None:
        cmd.extend(["--env-file", str(env_file)])
    for run_dir in previous_runs:
        cmd.extend(["--previous-generation-run", str(run_dir)])
    if resume_run is not None:
        cmd.extend(["--resume-generation-run", str(resume_run)])
    cmd.extend(extra_args)
    return cmd


def subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(repo_root() / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_path}{':' + existing_pythonpath if existing_pythonpath else ''}"
    return env


def run_generation_attempt(
    *,
    workspace_root: Path,
    classification_model: str,
    state_id: str,
    previous_runs: list[Path],
    resume_run: Path | None,
    batch_size: int,
    prompt_profile: str,
    model: str,
    env_file: Path | None,
    extra_args: list[str],
    board: ProgressBoard,
    attempt_label: str,
) -> subprocess.CompletedProcess[str]:
    cmd = build_generation_command(
        workspace_root=workspace_root,
        classification_model=classification_model,
        state_id=state_id,
        previous_runs=previous_runs,
        resume_run=resume_run,
        batch_size=batch_size,
        prompt_profile=prompt_profile,
        model=model,
        env_file=env_file,
        extra_args=extra_args,
    )
    log.info("Running generation attempt: %s", " ".join(cmd))
    board.set_active(state_id, attempt_label=attempt_label)
    board.render()

    process = subprocess.Popen(
        cmd,
        cwd=str(repo_root()),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=subprocess_env(),
    )
    try:
        while process.poll() is None:
            board.set_active(state_id, attempt_label=attempt_label)
            board.render()
            time.sleep(REFRESH_INTERVAL_SECONDS)
    finally:
        stdout, stderr = process.communicate()
        board.set_active(None)

    result = subprocess.CompletedProcess(
        args=cmd,
        returncode=process.returncode if process.returncode is not None else 1,
        stdout=stdout,
        stderr=stderr,
    )
    if result.returncode != 0:
        log.warning(
            "Macro state %s attempt exited %d stderr=%s",
            state_id,
            result.returncode,
            (stderr or "").strip()[:2000],
        )
    return result


def retry_macro_state(
    *,
    workspace_root: Path,
    classification_model: str,
    state_id: str,
    model: str,
    max_attempts: int,
    batch_sizes: tuple[int, ...],
    prompt_profile: str,
    env_file: Path | None,
    extra_args: list[str],
    board: ProgressBoard,
) -> dict[str, object]:
    started = time.monotonic()
    attempts: list[dict[str, object]] = []

    for attempt in range(1, max_attempts + 1):
        coverage = generation_coverage(
            workspace_root=workspace_root,
            state_id=state_id,
            model=model,
            classification_model=classification_model,
        )
        if coverage["complete"]:
            board.mark_result(state_id, "complete")
            board.render()
            return {
                "state_id": state_id,
                "status": "complete",
                "attempts": attempts,
                "coverage": coverage,
                "elapsed_seconds": time.monotonic() - started,
            }

        previous_runs = list_generation_runs(
            workspace_root,
            state_id,
            model=model,
        )
        resume_run = find_resumable_generation_run(
            workspace_root,
            state_id,
            model=model,
        )
        previous_for_attempt = [
            run_dir for run_dir in previous_runs
            if resume_run is None or run_dir != resume_run
        ]
        batch_size = batch_size_for_attempt(batch_sizes, attempt)
        attempt_label = (
            f"attempt {attempt}/{max_attempts}  missing={len(coverage['missing_ids'])}  "
            f"batch={batch_size}  runs={len(previous_runs)}"
            + ("  resume" if resume_run is not None else "")
        )
        log.info(
            "Macro state %s %s",
            state_id,
            attempt_label,
        )

        result = run_generation_attempt(
            workspace_root=workspace_root,
            classification_model=classification_model,
            state_id=state_id,
            previous_runs=previous_for_attempt,
            resume_run=resume_run,
            batch_size=batch_size,
            prompt_profile=prompt_profile,
            model=model,
            env_file=env_file,
            extra_args=extra_args,
            board=board,
            attempt_label=attempt_label,
        )

        attempt_record: dict[str, object] = {
            "attempt": attempt,
            "batch_size": batch_size,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        attempts.append(attempt_record)

        if result.stdout.strip():
            try:
                attempt_record["response"] = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

        coverage = generation_coverage(
            workspace_root=workspace_root,
            state_id=state_id,
            model=model,
            classification_model=classification_model,
        )
        attempt_record["coverage"] = coverage
        board.render()

        if coverage["complete"]:
            board.mark_result(state_id, "complete")
            board.render()
            return {
                "state_id": state_id,
                "status": "complete",
                "attempts": attempts,
                "coverage": coverage,
                "elapsed_seconds": time.monotonic() - started,
            }

    final_coverage = generation_coverage(
        workspace_root=workspace_root,
        state_id=state_id,
        model=model,
        classification_model=classification_model,
    )
    board.mark_result(state_id, "incomplete")
    board.render()
    return {
        "state_id": state_id,
        "status": "incomplete",
        "attempts": attempts,
        "coverage": final_coverage,
        "elapsed_seconds": time.monotonic() - started,
    }


def resolve_target_states(
    *,
    index: ScopeIndex,
    workspace_root: Path,
    classification_model: str,
    macro_state_ids: list[str],
) -> list[str]:
    if macro_state_ids:
        return sorted(macro_state_ids)

    targets: list[str] = []
    for state_id, _scope_state in index.states_with_microactions():
        if classification_path(
            workspace_root,
            state_id,
            classification_model=classification_model,
        ).exists():
            targets.append(state_id)
    return sorted(targets)


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
        "--macro-state-id",
        action="append",
        default=[],
        help="Macro state to generate (repeatable). Default: all classified macro states with microactions.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=8,
        help="Maximum generation attempts per macro state (default: 8).",
    )
    parser.add_argument(
        "--batch-sizes",
        type=parse_batch_sizes,
        default=DEFAULT_BATCH_SIZES,
        help="Comma-separated batch sizes to try across attempts (default: 6,2,1).",
    )
    parser.add_argument(
        "--prompt-profile",
        choices=("default", "slim"),
        default="slim",
        help="Prompt profile passed to generate_microaction_tasks.py (default: slim).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to generate with; progress is tracked per this model only.",
    )
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug file logging.")
    parser.add_argument(
        "extra_generate_args",
        nargs=argparse.REMAINDER,
        help="Extra args forwarded to generate_microaction_tasks.py (prefix with --).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_started = time.monotonic()
    run_timestamp = utc_run_timestamp()

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
    env_file = args.env_file or (root / ".env")
    extra_args = list(args.extra_generate_args)

    log_path = run_log_path(workspace_root, run_timestamp)
    configure_file_logging(log_path=log_path, verbose=args.verbose)

    try:
        openai_config = resolve_openai_config(env_path=env_file, model_override=args.model)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    model = openai_config["model"]
    index = ScopeIndex.load(repo_root=root)
    try:
        target_states = resolve_target_states(
            index=index,
            workspace_root=workspace_root,
            classification_model=classification_model,
            macro_state_ids=args.macro_state_id,
        )
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    if not target_states:
        print(json.dumps({
            "ok": False,
            "error": "no classified macro states found to generate",
        }, indent=2), file=sys.stderr)
        return 2

    log.info(
        "Retry generation model=%s model_dir=%s macro_states=%d max_attempts=%d "
        "batch_sizes=%s prompt_profile=%s log=%s",
        model,
        model_dir_name(model),
        len(target_states),
        args.max_attempts,
        args.batch_sizes,
        args.prompt_profile,
        log_path,
    )

    progress_path = log_path.parent / PROGRESS_FILENAME
    board = ProgressBoard(
        workspace_root=workspace_root,
        model=model,
        classification_model=classification_model,
        state_ids=target_states,
        progress_path=progress_path,
    )
    display_stream = resolve_display_stream()
    if display_stream is not None:
        print("Live progress on this terminal.", file=display_stream)
        print(f"Also mirrored to {progress_path}", file=display_stream)
    else:
        print(
            f"Progress table: tail -f {progress_path}",
            file=sys.stderr,
        )
    board.render()

    results: list[dict[str, object]] = []
    incomplete: list[str] = []
    for state_id in target_states:
        state_started = time.monotonic()
        log.info("stage=macro_state status=start macro_state_id=%s", state_id)
        try:
            result = retry_macro_state(
                workspace_root=workspace_root,
                classification_model=classification_model,
                state_id=state_id,
                model=model,
                max_attempts=args.max_attempts,
                batch_sizes=args.batch_sizes,
                prompt_profile=args.prompt_profile,
                env_file=env_file,
                extra_args=extra_args,
                board=board,
            )
            results.append(result)
            if result["status"] != "complete":
                incomplete.append(state_id)
            log.info(
                "stage=macro_state status=%s macro_state_id=%s elapsed=%.2fs",
                result["status"],
                state_id,
                time.monotonic() - state_started,
            )
        except FileNotFoundError as exc:
            log.error("Macro state %s: %s", state_id, exc)
            board.mark_result(state_id, "error", note=str(exc))
            board.render()
            incomplete.append(state_id)
            results.append({
                "state_id": state_id,
                "status": "error",
                "error": str(exc),
            })

    board.set_active(None)
    board.render()
    board.finalize()

    summary = {
        "ok": not incomplete,
        "workspace_root": str(workspace_root),
        "classification_model": classification_model,
        "model": model,
        "log_file": str(log_path),
        "macro_states": len(target_states),
        "complete": len(target_states) - len(incomplete),
        "incomplete": incomplete,
        "results": results,
        "elapsed_seconds": time.monotonic() - run_started,
    }
    log.info("stage=run status=done summary=%s", json.dumps({
        key: summary[key]
        for key in ("ok", "model", "macro_states", "complete", "incomplete", "elapsed_seconds")
    }))
    print(json.dumps(summary, indent=2))
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
