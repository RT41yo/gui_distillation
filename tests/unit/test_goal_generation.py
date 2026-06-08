from __future__ import annotations

from pathlib import Path

from ui_explorer.synthetic.cost_log import reconcile_cost_log_prompts
from ui_explorer.synthetic.generation_output import goal_variant_output_path, write_goal_outputs
from ui_explorer.synthetic.goal_source import (
    clear_incomplete_goal_outputs,
    enrich_goal_outputs,
    filter_microactions_with_complete_goals,
)
from ui_explorer.synthetic.osworld_conversion import deterministic_task_id
from ui_explorer.synthetic.schemas import validate_macrostate_goals_batch


def test_validate_macrostate_goals_batch_requires_matching_task_count() -> None:
    result = {
        "microactions": [
            {
                "micro_action_id": "abc123",
                "task_type": "list_manipulation",
                "goal": [
                    {
                        "task_index": 0,
                        "variants": [
                            {
                                "goal": "Disable spell checking",
                                "expected_outcome": "Spell checking is off.",
                            },
                            {
                                "goal": "Turn off spell checking",
                                "expected_outcome": "Spell checking is off.",
                            },
                        ],
                    }
                ],
            }
        ]
    }
    outputs = validate_macrostate_goals_batch(
        result,
        {"abc123"},
        expected_goal_counts={"abc123": 1},
        max_variant_count=4,
    )
    assert len(outputs["abc123"]["goal"][0]["variants"]) == 2


def test_enrich_goal_outputs_attaches_source_task_and_task_id() -> None:
    outputs = {
        "abc123": {
            "task_type": "list_manipulation",
            "goal": [
                {
                    "task_index": 0,
                    "variants": [
                        {
                            "goal": "Disable spell checking",
                            "expected_outcome": "Done",
                        }
                    ],
                }
            ],
        }
    }
    source_outputs = {
        "abc123": {
            "task_type": "list_manipulation",
            "task": [
                {
                    "instruction": "Local step",
                    "expected_outcome": "Done",
                    "preconditions": {
                        "description": "Ready",
                        "extras": [],
                    },
                }
            ],
        }
    }
    enriched = enrich_goal_outputs(
        outputs,
        source_outputs=source_outputs,
        source_task_generation_run="/tmp/task_run",
        run_timestamp="20260606T120000Z",
    )
    task_id = deterministic_task_id(
        run_timestamp="20260606T120000Z",
        micro_action_id="abc123",
        task_index=0,
    )
    assert enriched["abc123"]["goal"][0]["id"] == task_id
    assert enriched["abc123"]["goal"][0]["source_task"]["instruction"] == "Local step"
    assert enriched["abc123"]["goal"][0]["variants"][0]["goal"] == "Disable spell checking"


def test_write_goal_outputs_uses_variant_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260606T120000Z"
    run_dir.mkdir()
    task_id = deterministic_task_id(
        run_timestamp="20260606T120000Z",
        micro_action_id="abc123",
        task_index=0,
    )
    write_goal_outputs(
        run_dir,
        {
            "abc123": {
                "task_type": "list_manipulation",
                "goal": [
                    {
                        "id": task_id,
                        "task_index": 0,
                        "variants": [
                            {
                                "variant_index": 0,
                                "goal": "Disable spell checking",
                                "expected_outcome": "Done",
                            },
                            {
                                "variant_index": 1,
                                "goal": "Turn off spell checking",
                                "expected_outcome": "Done",
                            },
                        ],
                        "source_task": {
                            "instruction": "Local",
                            "expected_outcome": "Done",
                            "preconditions": {
                                "description": "Ready",
                                "extras": [],
                            },
                        },
                    }
                ],
            }
        },
    )
    variant_0 = goal_variant_output_path(run_dir, task_id, 0)
    variant_1 = goal_variant_output_path(run_dir, task_id, 1)
    assert variant_0.exists()
    assert variant_1.exists()
    assert variant_0.read_text(encoding="utf-8").count("Disable spell checking") >= 1


def test_clear_incomplete_goal_outputs_removes_partial_task_dirs(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260606T120000Z"
    task_id = deterministic_task_id(
        run_timestamp="20260606T120000Z",
        micro_action_id="abc123",
        task_index=0,
    )
    write_goal_outputs(
        run_dir,
        {
            "abc123": {
                "task_type": "list_manipulation",
                "goal": [
                    {
                        "id": task_id,
                        "task_index": 0,
                        "variants": [
                            {"goal": "A", "expected_outcome": "Done"},
                            {"goal": "B", "expected_outcome": "Done"},
                        ],
                    }
                ],
            }
        },
    )
    source_outputs = {
        "abc123": {
            "task_type": "list_manipulation",
            "task": [{"instruction": "x", "expected_outcome": "y", "preconditions": {"description": "z", "extras": []}}],
        }
    }
    cleared = clear_incomplete_goal_outputs(
        run_dir,
        {"abc123"},
        source_outputs,
        goal_variant_count=4,
    )
    assert cleared == [task_id]
    assert not (run_dir / "goals" / task_id).exists()


def test_filter_microactions_with_complete_goals(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260606T120000Z"
    task_id = deterministic_task_id(
        run_timestamp="20260606T120000Z",
        micro_action_id="abc123",
        task_index=0,
    )
    write_goal_outputs(
        run_dir,
        {
            "abc123": {
                "task_type": "list_manipulation",
                "goal": [
                    {
                        "id": task_id,
                        "task_index": 0,
                        "variants": [
                            {"goal": "A", "expected_outcome": "Done"},
                            {"goal": "B", "expected_outcome": "Done"},
                        ],
                    }
                ],
            }
        },
    )
    source_outputs = {
        "abc123": {
            "task_type": "list_manipulation",
            "task": [{"instruction": "x", "expected_outcome": "y", "preconditions": {"description": "z", "extras": []}}],
        },
        "def456": {
            "task_type": "list_manipulation",
            "task": [{"instruction": "a", "expected_outcome": "b", "preconditions": {"description": "c", "extras": []}}],
        },
    }
    remaining, skipped = filter_microactions_with_complete_goals(
        run_dir,
        {"abc123", "def456"},
        source_outputs,
        goal_variant_count=2,
    )
    assert remaining == {"def456"}
    assert "abc123" in skipped


def test_reconcile_cost_log_prompts_merges_legacy_goal_log(tmp_path: Path) -> None:
    task_log = tmp_path / "cost_task_generation.jsonl"
    goal_log = tmp_path / "cost_goal_generation.jsonl"
    task_log.write_text(
        '{"generation_run": "/ws/task_generation/run1", "cost": 1.0}\n',
        encoding="utf-8",
    )
    goal_log.write_text(
        '{"generation_run": "/ws/task_generation/run1", "cost": 2.0}\n',
        encoding="utf-8",
    )
    stats = reconcile_cost_log_prompts(tmp_path)
    assert stats["merged_from_legacy_goal"] == 1
    assert not goal_log.exists()
    lines = [line for line in task_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    assert all('"prompt"' in line for line in lines)
