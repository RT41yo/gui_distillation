from __future__ import annotations

import json
from pathlib import Path

from ui_explorer.synthetic.generation_output import (
    in_flight_generation_progress,
    in_flight_microaction_ids_from_run,
)
from ui_explorer.synthetic.generation_progress import (
    format_in_flight_detail,
    parse_attempt_batch_total,
    snapshot_macro_state,
)
from ui_explorer.synthetic.schemas import YIELD_BUCKETS


def _write_classification(root: Path, state_id: str, action_ids: list[str]) -> None:
    payload = {bucket: [] for bucket in YIELD_BUCKETS}
    payload["high"] = action_ids
    state_dir = root / state_id
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "yield_classification.json").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )


def _write_raw_batch(run_dir: Path, batch_index: int, action_ids: list[str]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "microactions": [
            {"micro_action_id": action_id, "task": []}
            for action_id in action_ids
        ]
    }
    (run_dir / f"raw_response_batch_{batch_index:03d}.json").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )


def test_in_flight_progress_counts_latest_unfinished_run(tmp_path: Path) -> None:
    state_id = "state123"
    model = "gpt-test"
    _write_classification(tmp_path, state_id, ["a1", "a2", "a3", "a4"])

    older = tmp_path / state_id / "generations" / model / "20260606T100000Z"
    _write_raw_batch(older, 1, ["a1"])

    newer = tmp_path / state_id / "generations" / model / "20260606T110000Z"
    _write_raw_batch(newer, 1, ["a1", "a2"])
    _write_raw_batch(newer, 2, ["a3"])

    progress = in_flight_generation_progress(
        classification_root=tmp_path,
        state_id=state_id,
        model=model,
    )
    assert progress is not None
    assert progress["microaction_count"] == 3
    assert progress["batches_done"] == 2
    assert set(progress["micro_action_ids"]) == {"a1", "a2", "a3"}


def test_in_flight_microaction_ids_from_run_deduplicates(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_raw_batch(run_dir, 1, ["a1", "a2"])
    _write_raw_batch(run_dir, 2, ["a2", "a3"])
    assert in_flight_microaction_ids_from_run(run_dir) == {"a1", "a2", "a3"}


def test_parse_attempt_batch_total() -> None:
    assert parse_attempt_batch_total("attempt 1/8  missing=40  batch=6  runs=1") == 7
    assert parse_attempt_batch_total("missing=5 batch=2") == 3


def test_snapshot_macro_state_includes_in_flight_detail(tmp_path: Path) -> None:
    state_id = "state123"
    model = "gpt-test"
    _write_classification(tmp_path, state_id, ["a1", "a2"])
    run_dir = tmp_path / state_id / "generations" / model / "20260606T120000Z"
    _write_raw_batch(run_dir, 1, ["a1", "a2"])

    row = snapshot_macro_state(
        classification_root=tmp_path,
        state_id=state_id,
        model=model,
        status="running",
        attempt_label="missing=2 batch=2 runs=0",
    )
    assert row.in_flight_count == 2
    assert row.in_flight_batches_done == 1
    assert row.in_flight_batches_total == 1
    assert format_in_flight_detail(row) == "+2 in-flight batch 1/1"
