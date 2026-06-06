from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from ui_explorer.synthetic.generation_output import (
    generation_coverage,
    in_flight_generation_progress,
)

ATTEMPT_BATCH_TOTAL_PATTERN = re.compile(r"missing=(\d+).*batch=(\d+)")


def parse_attempt_batch_total(attempt_label: str) -> int | None:
    match = ATTEMPT_BATCH_TOTAL_PATTERN.search(attempt_label)
    if match is None:
        return None
    missing = int(match.group(1))
    batch_size = int(match.group(2))
    if batch_size < 1:
        return None
    return math.ceil(missing / batch_size)


@dataclass
class MacroStateProgressSnapshot:
    state_id: str
    expected: int = 0
    successful: int = 0
    runs: int = 0
    status: str = "pending"
    note: str = ""
    in_flight_count: int = 0
    in_flight_batches_done: int = 0
    in_flight_batches_total: int | None = None


def snapshot_macro_state(
    *,
    workspace_root: Path,
    state_id: str,
    model: str,
    classification_model: str,
    status: str = "pending",
    note: str = "",
    attempt_label: str = "",
) -> MacroStateProgressSnapshot:
    try:
        coverage = generation_coverage(
            workspace_root=workspace_root,
            state_id=state_id,
            model=model,
            classification_model=classification_model,
        )
    except FileNotFoundError:
        return MacroStateProgressSnapshot(
            state_id=state_id,
            status="unclassified" if status not in {"running", "error"} else status,
            note=note,
        )

    row_status = status
    if status not in {"running", "error"}:
        if coverage["complete"]:
            row_status = "complete"
        elif coverage["successful_count"]:
            row_status = "partial"
        else:
            row_status = "pending"

    in_flight = in_flight_generation_progress(
        workspace_root=workspace_root,
        state_id=state_id,
        model=model,
    )
    in_flight_count = 0
    in_flight_batches_done = 0
    batches_total = parse_attempt_batch_total(attempt_label) if attempt_label else None
    if in_flight is not None:
        in_flight_batches_done = int(in_flight["batches_done"])
        metadata_batches_total = in_flight.get("batches_total")
        if isinstance(metadata_batches_total, int) and metadata_batches_total > 0:
            batches_total = metadata_batches_total
        if in_flight.get("source") == "metadata":
            in_flight_count = 0
        else:
            in_flight_count = int(in_flight["microaction_count"])

    return MacroStateProgressSnapshot(
        state_id=state_id,
        expected=int(coverage["expected_count"]),
        successful=int(coverage["successful_count"]),
        runs=len(coverage["generation_runs"]),
        status=row_status,
        note=note,
        in_flight_count=in_flight_count,
        in_flight_batches_done=in_flight_batches_done,
        in_flight_batches_total=batches_total,
    )


def resolve_row_status(
    row: MacroStateProgressSnapshot,
    *,
    in_flight: dict[str, object] | None,
) -> str:
    if row.expected and row.successful >= row.expected:
        return "complete"
    if in_flight is not None:
        return "running"
    if row.successful > 0:
        return "partial"
    return row.status if row.status not in {"", "pending"} else "pending"


def format_progress_bar(current: int, total: int, *, width: int = 20) -> str:
    if total <= 0:
        return "░" * width
    clamped = max(0, min(current, total))
    filled = int(round((clamped / total) * width))
    filled = min(filled, width)
    return ("█" * filled) + ("░" * (width - filled))


def macro_state_progress_counts(
    row: MacroStateProgressSnapshot,
) -> tuple[int, int, int, int | None]:
    """Return (micro_done, micro_total, batches_done, batches_total)."""
    micro_done = row.successful + row.in_flight_count
    micro_total = row.expected
    batches_done = row.in_flight_batches_done
    batches_total = row.in_flight_batches_total
    return micro_done, micro_total, batches_done, batches_total


def format_macro_state_bar_line(
    row: MacroStateProgressSnapshot,
    *,
    width: int = 20,
    status: str | None = None,
) -> str:
    resolved_status = status or row.status
    micro_done, micro_total, batches_done, batches_total = macro_state_progress_counts(row)
    micro_bar = format_progress_bar(micro_done, micro_total, width=width)
    if batches_total is not None and batches_total > 0:
        batch_bar = format_progress_bar(batches_done, batches_total, width=max(8, width // 2))
        batch_label = f"{batches_done}/{batches_total}"
    elif batches_done > 0:
        batch_bar = format_progress_bar(batches_done, batches_done, width=max(8, width // 2))
        batch_label = f"{batches_done}/?"
    else:
        batch_bar = format_progress_bar(0, 1, width=max(8, width // 2))
        batch_label = "0/?"

    micro_label = f"{min(micro_done, micro_total) if micro_total else micro_done}/{micro_total}"
    return (
        f"{row.state_id}  {micro_bar}  {micro_label:>7}  "
        f"batch {batch_bar} {batch_label:>5}  {resolved_status}"
    )


def status_sort_key(status: str) -> int:
    return {
        "running": 0,
        "partial": 1,
        "pending": 2,
        "error": 3,
        "unclassified": 4,
        "complete": 5,
    }.get(status, 6)


def format_in_flight_detail(row: MacroStateProgressSnapshot) -> str:
    if row.in_flight_batches_done <= 0 and row.in_flight_count <= 0:
        return ""
    if row.in_flight_count > 0:
        batch_label = str(row.in_flight_batches_done)
        if row.in_flight_batches_total is not None:
            batch_label = f"{row.in_flight_batches_done}/{row.in_flight_batches_total}"
        return f"+{row.in_flight_count} uncommitted batch {batch_label}"
    if row.in_flight_batches_done <= 0:
        return ""
    batch_label = str(row.in_flight_batches_done)
    if row.in_flight_batches_total is not None:
        batch_label = f"{row.in_flight_batches_done}/{row.in_flight_batches_total}"
    return f"batch {batch_label}"


def format_progress_lines(
    *,
    model: str,
    rows: list[MacroStateProgressSnapshot],
    elapsed_seconds: float,
    active_state_id: str | None = None,
    attempt_label: str = "",
) -> list[str]:
    total_expected = sum(row.expected for row in rows)
    total_successful = sum(row.successful for row in rows)
    total_in_flight = sum(row.in_flight_count for row in rows)
    complete_states = sum(
        1 for row in rows
        if row.expected and row.successful >= row.expected
    )

    microaction_summary = f"microactions={total_successful}/{total_expected}"
    if total_in_flight:
        microaction_summary += f" ({total_in_flight} uncommitted)"

    lines = [
        (
            f"Generation retry  model={model}  "
            f"states={complete_states}/{len(rows)}  "
            f"{microaction_summary}  "
            f"elapsed={elapsed_seconds:,.0f}s"
        ),
    ]
    if active_state_id:
        lines.append(
            f"Active: {active_state_id}"
            + (f"  {attempt_label}" if attempt_label else "")
        )
    lines.append("")
    lines.append(f"{'Macro state':<14} {'Done':>5} {'Total':>5} {'Runs':>4}  Status")
    lines.append("-" * 68)
    for row in rows:
        status = row.status
        if row.expected and row.successful >= row.expected:
            status = "complete"
        in_flight_detail = format_in_flight_detail(row)
        note_parts: list[str] = []
        if in_flight_detail and status == "running":
            note_parts.append(in_flight_detail)
        if row.note and status == "running":
            note_parts.append(row.note)
        note = f" ({'; '.join(note_parts)})" if note_parts else ""
        lines.append(
            f"{row.state_id:<14} {row.successful:>5} {row.expected:>5} {row.runs:>4}  "
            f"{status}{note}"
        )
    return lines
