"""
Step record builder — assembles a StepRecord from agent step components.
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from src.domain.models import (
    DHashRecord,
    ExecutorAction,
    IoURecord,
    LocatorResult,
    PlannerResponse,
    StepRecord,
)


def make_timestamp() -> str:
    """Return timestamp string in DART format: YYYYMMDD@HHMMSSffffff."""
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d@%H%M%S") + f"{now.microsecond:06d}"


def build_step_record(
    step_id: int,
    task_id: str,
    app_id: str,
    task_text: str,
    screenshot_file: str,
    a11y_tree_file: Optional[str],
    a11y_buttons_file: Optional[str],
    planner_response: Optional[PlannerResponse],
    primary_locator: Optional[LocatorResult],
    executor_action: Optional[ExecutorAction],
    tool_calls: List[str],
    iou: Optional[IoURecord],
    dhash: Optional[DHashRecord],
    done: bool,
    step_reward: float = 0.0,
) -> StepRecord:
    """Assemble a StepRecord from the components produced during one agent step."""
    planner_action_str: Optional[str] = None
    if planner_response:
        if planner_response.action_type.value == "type_text":
            planner_action_str = f"type_text('{planner_response.text}')"
        elif planner_response.action_type.value == "hotkey":
            planner_action_str = f"hotkey({planner_response.keys})"
        else:
            planner_action_str = (
                f"{planner_response.action_type.value}"
                f"('{planner_response.target_query}')"
            )

    return StepRecord(
        step_id=step_id,
        task_id=task_id,
        app_id=app_id,
        task_text=task_text,
        timestamp=make_timestamp(),
        screenshot_file=screenshot_file,
        a11y_tree_file=a11y_tree_file,
        a11y_buttons_file=a11y_buttons_file,
        planner_raw_response=planner_response.raw_response if planner_response else None,
        planner_thought=planner_response.thought if planner_response else None,
        planner_action=planner_action_str,
        locator_source=primary_locator.source if primary_locator else None,
        locator_result=primary_locator,
        executor_action=executor_action,
        tool_calls=tool_calls,
        iou=iou,
        dhash=dhash,
        done=done,
        step_reward=step_reward,
    )
