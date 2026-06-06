from __future__ import annotations

import json
from pathlib import Path

from ui_explorer.synthetic.generation_output import (
    GENERATION_STATUS_GENERATED,
    GENERATION_STATUS_IN_PROGRESS,
    RAW_SUBDIR,
    commit_generation_checkpoint,
    find_resumable_generation_run,
    generation_coverage,
    load_generation_run_state,
    successful_action_ids_from_generation_run,
)
from ui_explorer.synthetic.paths import CLASSIFICATION_DIRNAME, TASK_GENERATION_DIRNAME
from ui_explorer.synthetic.schemas import YIELD_BUCKETS


def _write_classification(root: Path, state_id: str, action_ids: list[str], *, model: str = "gpt-test") -> None:
    payload = {bucket: [] for bucket in YIELD_BUCKETS}
    payload["high"] = action_ids
    state_dir = root / CLASSIFICATION_DIRNAME / model / state_id
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "yield_classification.json").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )


def _checkpoint_metadata(
    *,
    requested: list[str],
    successful: list[str],
    status: str = GENERATION_STATUS_IN_PROGRESS,
    batches: list[dict] | None = None,
) -> dict:
    return {
        "status": status,
        "requested_micro_action_ids": requested,
        "successful_micro_action_ids": successful,
        "failed_micro_action_ids": [],
        "successful_microactions": [],
        "failed_microactions": [],
        "batches": batches or [],
        "usage": {
            "num_tokens": 0,
            "cost": 0.0,
            "cost_source": "mixed",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "api_calls": 0,
        },
        "batch_size": 2,
        "model": "gpt-test",
        "macro_state_id": "state123",
    }


def test_commit_checkpoint_updates_coverage_incrementally(tmp_path: Path) -> None:
    state_id = "state123"
    model = "gpt-test"
    _write_classification(tmp_path, state_id, ["a1", "a2", "a3"])

    run_dir = tmp_path / TASK_GENERATION_DIRNAME / model / state_id / "20260606T120000Z"
    settings = {
        "timestamp": "20260606T120000Z",
        "status": GENERATION_STATUS_IN_PROGRESS,
        "macro_state_id": state_id,
        "micro_action_ids": ["a1", "a2", "a3"],
        "model": model,
    }
    commit_generation_checkpoint(
        run_dir=run_dir,
        settings=settings,
        metadata=_checkpoint_metadata(requested=["a1", "a2", "a3"], successful=["a1"]),
        new_outputs={
            "a1": {
                "micro_action_id": "a1",
                "task_type": "click",
                "task": [{"instruction": "do a1"}],
            }
        },
    )

    coverage = generation_coverage(
        workspace_root=tmp_path,
        state_id=state_id,
        model=model,
        classification_model=model,
    )
    assert coverage["successful_count"] == 1
    assert successful_action_ids_from_generation_run(run_dir) == {"a1"}
    assert (run_dir / RAW_SUBDIR / "metadata.json").exists()
    assert (run_dir / RAW_SUBDIR / "a1.json").exists()


def test_find_resumable_generation_run_prefers_in_progress(tmp_path: Path) -> None:
    state_id = "state123"
    model = "gpt-test"
    _write_classification(tmp_path, state_id, ["a1"])

    finalized = tmp_path / TASK_GENERATION_DIRNAME / model / state_id / "20260606T100000Z"
    commit_generation_checkpoint(
        run_dir=finalized,
        settings={"timestamp": "20260606T100000Z", "status": GENERATION_STATUS_GENERATED},
        metadata=_checkpoint_metadata(
            requested=["a1"],
            successful=["a1"],
            status=GENERATION_STATUS_GENERATED,
        ),
    )

    in_progress = tmp_path / TASK_GENERATION_DIRNAME / model / state_id / "20260606T110000Z"
    commit_generation_checkpoint(
        run_dir=in_progress,
        settings={"timestamp": "20260606T110000Z", "status": GENERATION_STATUS_IN_PROGRESS},
        metadata=_checkpoint_metadata(requested=["a1"], successful=[]),
    )

    assert find_resumable_generation_run(tmp_path, state_id, model=model) == in_progress


def test_load_generation_run_state_reads_committed_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / TASK_GENERATION_DIRNAME / "gpt-test" / "state123" / "20260606T120000Z"
    commit_generation_checkpoint(
        run_dir=run_dir,
        settings={"timestamp": "20260606T120000Z"},
        metadata=_checkpoint_metadata(requested=["a1", "a2"], successful=["a1"]),
        new_outputs={
            "a1": {
                "micro_action_id": "a1",
                "task_type": "click",
                "task": [{"instruction": "do a1"}],
            }
        },
    )

    state = load_generation_run_state(run_dir)
    assert set(state["outputs"]) == {"a1"}
    assert state["metadata"]["status"] == GENERATION_STATUS_IN_PROGRESS
