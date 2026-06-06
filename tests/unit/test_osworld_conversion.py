from __future__ import annotations

import json
from pathlib import Path

from ui_explorer.synthetic.generation_output import (
    RAW_SUBDIR,
    commit_generation_checkpoint,
    migrate_run_raw_layout,
)
from ui_explorer.synthetic.osworld_conversion import (
    OSWORLD_DUMMY_EVALUATOR_FUNC,
    convert_generation_run,
    deterministic_task_id,
    infer_snapshot_from_workspace,
)
from ui_explorer.synthetic.paths import TASK_GENERATION_DIRNAME


def test_infer_snapshot_from_workspace() -> None:
    root = Path("data/synthetic/libreoffice_writer/active_root_231")
    assert infer_snapshot_from_workspace(root) == "libreoffice_writer"


def test_deterministic_task_id_is_stable() -> None:
    first = deterministic_task_id(
        run_timestamp="20260606T195618Z",
        micro_action_id="070b4298960c7e57",
        task_index=0,
    )
    second = deterministic_task_id(
        run_timestamp="20260606T195618Z",
        micro_action_id="070b4298960c7e57",
        task_index=0,
    )
    assert first == second
    assert first != deterministic_task_id(
        run_timestamp="20260606T195618Z",
        micro_action_id="070b4298960c7e57",
        task_index=1,
    )


def test_migrate_run_raw_layout_moves_flat_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / TASK_GENERATION_DIRNAME / "gpt-test" / "state123" / "20260606T120000Z"
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.json").write_text(json.dumps({"status": "generated"}) + "\n", encoding="utf-8")
    (run_dir / "a100000000000001.json").write_text(
        json.dumps({
            "micro_action_id": "a100000000000001",
            "task_type": "click",
            "task": [{"instruction": "do a1", "expected_outcome": "done", "preconditions": {"description": "x", "extras": []}}],
        }) + "\n",
        encoding="utf-8",
    )

    result = migrate_run_raw_layout(run_dir)
    assert result is not None
    assert result["already_migrated"] is False
    assert (run_dir / RAW_SUBDIR / "metadata.json").exists()
    assert (run_dir / RAW_SUBDIR / "a100000000000001.json").exists()
    assert not (run_dir / "metadata.json").exists()


def test_convert_generation_run_writes_osworld_tasks(tmp_path: Path) -> None:
    workspace_root = tmp_path / "data" / "synthetic" / "libreoffice_writer" / "active_root_231"
    run_dir = workspace_root / TASK_GENERATION_DIRNAME / "gpt-test" / "state123" / "20260606T120000Z"
    commit_generation_checkpoint(
        run_dir=run_dir,
        settings={"timestamp": "20260606T120000Z", "macro_state_id": "state123"},
        metadata={
            "status": "generated",
            "macro_state_id": "state123",
            "successful_micro_action_ids": ["070b4298960c7e57"],
        },
        new_outputs={
            "070b4298960c7e57": {
                "micro_action_id": "070b4298960c7e57",
                "task_type": "cursor_format_toggle",
                "task": [{
                    "instruction": "Turn italic on.",
                    "expected_outcome": "Text is italic.",
                    "preconditions": {"description": "blank doc", "extras": []},
                }],
            }
        },
    )

    result = convert_generation_run(run_dir, workspace_root=workspace_root)
    assert result["converted_count"] == 1
    output_path = Path(result["converted"][0]["path"])
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["snapshot"] == "libreoffice_writer"
    assert payload["instruction"] == "Turn italic on."
    assert payload["evaluator"]["func"] == OSWORLD_DUMMY_EVALUATOR_FUNC
    assert payload["synthetic"]["micro_action_id"] == "070b4298960c7e57"
    assert payload["trajectory"] == "trajectories/"
    assert payload["config"][0]["type"] == "upload_file"
    assert payload["config"][1]["type"] == "open"
    assert Path(payload["config"][0]["parameters"]["files"][0]["local_path"]).exists()
    assert payload["synthetic"]["fixture"] == "blank.docx"
    assert payload["synthetic"]["macrostate_setup"]["status"] == "unsupported"


def test_convert_generation_run_adds_a11y_preflight_for_known_macro_state(tmp_path: Path) -> None:
    workspace_root = Path("data/synthetic/libreoffice_writer/active_root_231")
    if not workspace_root.exists():
        pytest.skip("writer workspace maps unavailable")

    run_dir = workspace_root / TASK_GENERATION_DIRNAME / "gpt-test" / "36427b830db2" / "20260606T999999Z"
    commit_generation_checkpoint(
        run_dir=run_dir,
        settings={"timestamp": "20260606T999999Z", "macro_state_id": "36427b830db2"},
        metadata={
            "status": "generated",
            "macro_state_id": "36427b830db2",
            "successful_micro_action_ids": ["070b4298960c7e57"],
        },
        new_outputs={
            "070b4298960c7e57": {
                "micro_action_id": "070b4298960c7e57",
                "task_type": "cursor_format_toggle",
                "task": [{
                    "instruction": "Turn italic on.",
                    "expected_outcome": "Text is italic.",
                    "preconditions": {"description": "blank doc", "extras": []},
                }],
            }
        },
    )

    result = convert_generation_run(run_dir, workspace_root=workspace_root, overwrite=True)
    payload = json.loads(Path(result["converted"][0]["path"]).read_text(encoding="utf-8"))
    config_types = [step["type"] for step in payload["config"]]
    assert config_types[:2] == ["upload_file", "open"]
    assert "activate_window" in config_types
    assert "a11y_preflight" in config_types
    assert payload["synthetic"]["macrostate_setup"]["status"] == "ready"
