"""
Unit tests for the gui2mcp agent (TZ section 19).

Tests:
  1. app_basket.yaml loading
  2. task_basket.yaml loading
  3. A11Y element lookup (from XML fixture)
  4. Planner response parsing
  5. EpisodeRecord construction
  6. DART export
  7. Summary export
"""
from __future__ import annotations

import json
import textwrap
import uuid
from pathlib import Path

import pytest

from src.domain.app_registry import AppRegistry
from src.domain.models import (
    ActionType,
    AppConfig,
    EpisodeRecord,
    ExecutorAction,
    IoURecord,
    LocatorResult,
    PlannerResponse,
    StepRecord,
    TaskConfig,
)
from src.domain.task_registry import TaskRegistry
from src.exporters.dart_exporter import DartExporter
from src.exporters.summary_exporter import SummaryExporter
from src.storage.episode_record import EpisodeRecordBuilder
from src.storage.step_record import build_step_record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_basket_yaml(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
        apps:
          - app_id: calc
            display_name: GNOME Calculator
            launcher: gnome-calculator
            a11y_app_name: gnome-calculator
            mode: a11y_first
            evaluator: calc_evaluator
          - app_id: gedit
            display_name: gedit Text Editor
            launcher: gedit
            a11y_app_name: gedit
            mode: a11y_first
            evaluator: gedit_evaluator
    """)
    p = tmp_path / "app_basket.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def task_basket_yaml(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
        tasks:
          calc:
            - task_id: calc_001
              instruction: "Compute 17 + 25"
              category: arithmetic
              evaluator: display_equals_42
            - task_id: calc_002
              instruction: "Compute 9 * 6"
              category: arithmetic
              evaluator: display_equals_54
          gedit:
            - task_id: gedit_001
              instruction: "Type Hello"
              category: text_edit
              evaluator: gedit_contains_text
              expected_text: "Hello"
    """)
    p = tmp_path / "task_basket.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def a11y_xml(tmp_path: Path) -> Path:
    xml = textwrap.dedent("""\
        <accessibility-tree app="gnome-calculator">
          <element role="push button" name="1" x="100" y="200" width="50" height="50"/>
          <element role="push button" name="plus" x="200" y="200" width="50" height="50"/>
          <element role="label" name="0" x="50" y="50" width="200" height="40"/>
        </accessibility-tree>
    """)
    p = tmp_path / "a11y_test.xml"
    p.write_text(xml)
    return p


@pytest.fixture
def sample_app() -> AppConfig:
    return AppConfig(
        app_id="calc",
        display_name="GNOME Calculator",
        launcher="gnome-calculator",
        a11y_app_name="gnome-calculator",
        mode="a11y_first",
        evaluator="calc_evaluator",
    )


@pytest.fixture
def sample_task() -> TaskConfig:
    return TaskConfig(
        task_id="calc_001",
        instruction="Compute 17 + 25",
        category="arithmetic",
        evaluator="display_equals_42",
    )


@pytest.fixture
def sample_step(sample_app: AppConfig, sample_task: TaskConfig) -> StepRecord:
    planner = PlannerResponse(
        thought="I should click 1",
        target_query="1",
        action_type=ActionType.CLICK,
        done=False,
    )
    locator = LocatorResult(
        source="a11y",
        found=True,
        element_name="1",
        bbox=[100.0, 200.0, 50.0, 50.0],
        center=(125.0, 225.0),
        confidence=1.0,
    )
    executor = ExecutorAction(tool="click", x=125.0, y=225.0)
    return build_step_record(
        step_id=0,
        task_id=sample_task.task_id,
        app_id=sample_app.app_id,
        task_text=sample_task.instruction,
        screenshot_file="step_0000.png",
        a11y_tree_file="a11y_step_0000.xml",
        a11y_buttons_file="a11y_step_0000.txt",
        planner_response=planner,
        primary_locator=locator,
        executor_action=executor,
        tool_calls=["take_screenshot", "get_a11y_tree", "find_element_a11y", "click"],
        iou=IoURecord(a11y_bbox=[100.0, 200.0, 50.0, 50.0], vlm_bbox=[102.0, 198.0, 50.0, 50.0], iou_score=0.92),
        dhash=None,
        done=False,
    )


# ---------------------------------------------------------------------------
# Test 1: app_basket.yaml loading
# ---------------------------------------------------------------------------

def test_app_registry_loads(app_basket_yaml: Path) -> None:
    registry = AppRegistry(app_basket_yaml)
    assert "calc" in registry.app_ids()
    assert "gedit" in registry.app_ids()
    app = registry.get("calc")
    assert app.display_name == "GNOME Calculator"
    assert app.launcher == "gnome-calculator"


def test_app_registry_unknown_raises(app_basket_yaml: Path) -> None:
    registry = AppRegistry(app_basket_yaml)
    with pytest.raises(KeyError):
        registry.get("chrome")


# ---------------------------------------------------------------------------
# Test 2: task_basket.yaml loading
# ---------------------------------------------------------------------------

def test_task_registry_loads(task_basket_yaml: Path) -> None:
    registry = TaskRegistry(task_basket_yaml)
    tasks = registry.list("calc")
    assert len(tasks) == 2
    t = registry.get("calc", "calc_001")
    assert t.instruction == "Compute 17 + 25"
    assert t.evaluator == "display_equals_42"


def test_task_registry_random(task_basket_yaml: Path) -> None:
    registry = TaskRegistry(task_basket_yaml)
    task = registry.select_random("gedit")
    assert task.task_id == "gedit_001"


def test_task_registry_unknown_raises(task_basket_yaml: Path) -> None:
    registry = TaskRegistry(task_basket_yaml)
    with pytest.raises(KeyError):
        registry.get("calc", "calc_999")


# ---------------------------------------------------------------------------
# Test 3: A11Y element lookup
# ---------------------------------------------------------------------------

def test_a11y_find_button(a11y_xml: Path) -> None:
    from src.core.a11y_capture import A11YCapture
    capture = A11YCapture()
    result = capture.find_button_by_name(a11y_xml, "1")
    assert result is not None
    x, y, w, h = result
    assert x == 100
    assert y == 200
    assert w == 50
    assert h == 50


def test_a11y_find_button_missing(a11y_xml: Path) -> None:
    from src.core.a11y_capture import A11YCapture
    capture = A11YCapture()
    result = capture.find_button_by_name(a11y_xml, "nonexistent_button_xyz")
    assert result is None


# ---------------------------------------------------------------------------
# Test 4: Planner response parsing
# ---------------------------------------------------------------------------

def test_planner_parse_valid() -> None:
    from src.agents.planner import Planner

    class _FakeClient:
        pass

    planner = Planner.__new__(Planner)
    planner._prompt_template = ""
    planner._client = None  # type: ignore[assignment]

    raw = json.dumps({
        "thought": "I need to click settings",
        "target_query": "Settings",
        "action_type": "click",
        "done": False,
    })
    resp = planner._parse(raw)
    assert resp.thought == "I need to click settings"
    assert resp.target_query == "Settings"
    assert resp.action_type == ActionType.CLICK
    assert resp.done is False


def test_planner_parse_done() -> None:
    from src.agents.planner import Planner

    planner = Planner.__new__(Planner)
    planner._prompt_template = ""
    planner._client = None  # type: ignore[assignment]

    raw = json.dumps({
        "thought": "Task complete",
        "target_query": "",
        "action_type": "click",
        "done": True,
    })
    resp = planner._parse(raw)
    assert resp.done is True
    assert resp.action_type == ActionType.DONE


def test_planner_parse_invalid_json() -> None:
    from src.agents.planner import Planner

    planner = Planner.__new__(Planner)
    planner._prompt_template = ""
    planner._client = None  # type: ignore[assignment]

    resp = planner._parse("not json at all {{{")
    assert resp.action_type == ActionType.WAIT


# ---------------------------------------------------------------------------
# Test 5: EpisodeRecord construction
# ---------------------------------------------------------------------------

def test_episode_record_construction(
    sample_app: AppConfig,
    sample_task: TaskConfig,
    sample_step: StepRecord,
) -> None:
    builder = EpisodeRecordBuilder(sample_app, sample_task)
    builder.add_step(sample_step)
    episode = builder.finalize(final_score=1.0, success=True)

    assert episode.app_id == "calc"
    assert episode.task_id == "calc_001"
    assert episode.total_steps == 1
    assert episode.final_score == 1.0
    assert episode.success is True
    assert len(episode.steps) == 1
    assert episode.locator_source_counts.get("a11y") == 1


# ---------------------------------------------------------------------------
# Test 6: DART export
# ---------------------------------------------------------------------------

def test_dart_export(
    tmp_path: Path,
    sample_app: AppConfig,
    sample_task: TaskConfig,
    sample_step: StepRecord,
) -> None:
    # Create a fake screenshot
    episode_uuid = str(uuid.uuid4())
    internal_dir = tmp_path / "internal" / episode_uuid
    internal_dir.mkdir(parents=True)
    fake_png = internal_dir / "step_0000.png"
    fake_png.write_bytes(b"\x89PNG\r\n")  # minimal fake PNG

    builder = EpisodeRecordBuilder(sample_app, sample_task)
    builder.add_step(sample_step)
    episode = builder.finalize(final_score=1.0, success=True)
    # Override uuid to match our dir
    episode = episode.model_copy(update={"episode_uuid": episode_uuid})

    dart_root = tmp_path / "dart"
    exporter = DartExporter()
    bundle_dir = exporter.export(episode, dart_root, internal_dir)

    assert bundle_dir.exists()
    traj = bundle_dir / "traj.jsonl"
    result = bundle_dir / "result.txt"
    assert traj.exists()
    assert result.exists()
    assert result.read_text().strip() == "1.0"

    rows = [json.loads(line) for line in traj.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["step_num"] == 1
    assert rows[0]["done"] is False


# ---------------------------------------------------------------------------
# Test 7: Summary export
# ---------------------------------------------------------------------------

def test_summary_export(tmp_path: Path) -> None:
    # Build a minimal DART tree with two episodes
    for app_id in ("calc", "gedit"):
        for i in range(2):
            ep_uuid = str(uuid.uuid4())
            bundle = (
                tmp_path
                / "pyautogui" / "screenshot" / "gui2mcp_agent"
                / app_id / ep_uuid
            )
            bundle.mkdir(parents=True)
            score = 1.0 if i == 0 else 0.0
            (bundle / "result.txt").write_text(str(score))
            (bundle / "traj.jsonl").write_text("")

    exporter = SummaryExporter()
    exporter.export(tmp_path)

    all_result_path = tmp_path / "pyautogui" / "screenshot" / "gui2mcp_agent" / "all_result.json"
    results_path = tmp_path / "summary" / "results.json"

    assert all_result_path.exists()
    assert results_path.exists()

    all_result = json.loads(all_result_path.read_text())
    assert "calc" in all_result
    assert "gedit" in all_result
    assert len(all_result["calc"]) == 2

    results = json.loads(results_path.read_text())
    assert len(results) == 4
    apps = {r["application"] for r in results}
    assert apps == {"calc", "gedit"}
