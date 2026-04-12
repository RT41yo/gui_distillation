"""
Episode controller — runs the step loop for a single episode.

Orchestrates:
  1. Screenshot capture
  2. A11Y tree capture
  3. Planner call → PlannerResponse
  4. A11Y element location
  5. VLM element location (parallel, for IoU)
  6. IoU + dHash computation
  7. Action execution
  8. Step record assembly + persistence
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from src.agents.planner import Planner
from src.domain.models import (
    ActionType,
    AppConfig,
    EpisodeRecord,
    LocatorResult,
    TaskConfig,
)
from src.evaluation.dhash_evaluator import compute_dhash_record, plot_hamming_chart
from src.evaluation.iou_evaluator import compute_iou
from src.executor.action_executor import ActionExecutor
from src.mcp_servers.tools.a11y_tool import FindElementA11YTool, FindElementA11YInput, GetA11YTreeTool, GetA11YTreeInput
from src.mcp_servers.tools.vision_tool import FindElementVLMTool, FindElementVLMInput, TakeScreenshotTool, TakeScreenshotInput
from src.perception.a11y_service import A11YService
from src.storage.artifact_store import ArtifactStore
from src.storage.episode_record import EpisodeRecordBuilder
from src.storage.step_record import build_step_record, make_timestamp

logger = logging.getLogger(__name__)


class EpisodeController:
    """
    Runs one full episode: step loop → returns EpisodeRecord (without evaluation).

    Evaluation is done by the caller (Gui2MCPAgent) after this returns.
    """

    def __init__(
        self,
        app: AppConfig,
        task: TaskConfig,
        planner: Planner,
        screenshot_tool: TakeScreenshotTool,
        a11y_tree_tool: GetA11YTreeTool,
        find_a11y_tool: FindElementA11YTool,
        find_vlm_tool: FindElementVLMTool,
        executor: ActionExecutor,
        artifact_store: ArtifactStore,
        max_steps: int = 20,
    ) -> None:
        self._app = app
        self._task = task
        self._planner = planner
        self._screenshot_tool = screenshot_tool
        self._a11y_tree_tool = a11y_tree_tool
        self._find_a11y_tool = find_a11y_tool
        self._find_vlm_tool = find_vlm_tool
        self._executor = executor
        self._store = artifact_store
        self._max_steps = max_steps

    def run(self) -> EpisodeRecord:
        """Execute the episode step loop and return the raw EpisodeRecord."""
        builder = EpisodeRecordBuilder(self._app, self._task)
        action_history: List[str] = []
        hamming_distances: List[Optional[int]] = []

        for step_id in range(self._max_steps):
            logger.info("=== Step %d / %d ===", step_id, self._max_steps - 1)
            tool_calls: List[str] = []

            # 1. Screenshot
            screenshot_path = self._store.screenshot_path(step_id)
            self._screenshot_tool.run(TakeScreenshotInput(output_path=screenshot_path))
            tool_calls.append("take_screenshot")

            # 2. A11Y tree
            a11y_out = self._a11y_tree_tool.run(
                GetA11YTreeInput(output_dir=self._store.episode_dir, step_id=step_id)
            )
            xml_path = a11y_out.xml_path
            txt_path = a11y_out.txt_path
            tool_calls.append("get_a11y_tree")

            a11y_elements = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""

            # 3. Planner
            planner_resp = self._planner.plan(
                task_instruction=self._task.instruction,
                app_display_name=self._app.display_name,
                step_num=step_id + 1,
                max_steps=self._max_steps,
                a11y_elements=a11y_elements,
                action_history=action_history,
                screenshot_path=screenshot_path,
            )
            tool_calls.append("planner")

            # 4. A11Y locator (primary)
            a11y_result: LocatorResult
            if planner_resp.action_type in (ActionType.CLICK, ActionType.SCROLL):
                a11y_result = self._find_a11y_tool.run(
                    FindElementA11YInput(xml_path=xml_path, query=planner_resp.target_query)
                )
                tool_calls.append("find_element_a11y")
            else:
                a11y_result = LocatorResult(source="a11y", found=False)

            # 5. VLM locator (always called for IoU)
            vlm_result = self._find_vlm_tool.run(
                FindElementVLMInput(
                    screenshot_path=screenshot_path,
                    query=planner_resp.target_query,
                )
            )
            tool_calls.append("find_element_vlm")

            # 6. IoU
            iou_record = compute_iou(a11y_result, vlm_result)

            # 7. dHash (before screenshot already taken; after will be taken post-action)
            after_path = self._store.screenshot_path(step_id + 1) if step_id + 1 < self._max_steps else None

            # 8. Execute action
            primary_locator = a11y_result if a11y_result.found else vlm_result
            done = planner_resp.done or planner_resp.action_type == ActionType.DONE

            executor_action = None
            if not done:
                try:
                    executor_action = self._executor.execute(planner_resp, primary_locator)
                    tool_calls.append(executor_action.tool)
                except Exception as exc:
                    logger.error("Executor failed at step %d: %s", step_id, exc)
                    done = True

            # 9. dHash: capture after screenshot and compute
            if after_path and not done:
                self._screenshot_tool.run(TakeScreenshotInput(output_path=after_path))
            dhash_record = compute_dhash_record(screenshot_path, after_path)
            hamming_distances.append(dhash_record.hamming_distance)

            # 10. Build and persist step record
            step = build_step_record(
                step_id=step_id,
                task_id=self._task.task_id,
                app_id=self._app.app_id,
                task_text=self._task.instruction,
                screenshot_file=screenshot_path.name,
                a11y_tree_file=xml_path.name if xml_path.exists() else None,
                a11y_buttons_file=txt_path.name if txt_path.exists() else None,
                planner_response=planner_resp,
                primary_locator=primary_locator,
                executor_action=executor_action,
                tool_calls=tool_calls,
                iou=iou_record,
                dhash=dhash_record,
                done=done,
            )
            builder.add_step(step)
            self._store.write_step(step_id, step.model_dump())

            action_history.append(
                f"Step {step_id}: {planner_resp.action_type.value}('{planner_resp.target_query}')"
                f" — thought: {planner_resp.thought[:60]}"
            )

            if done:
                logger.info("Episode done at step %d", step_id)
                break

        # Plot Hamming chart
        chart_path = self._store.episode_dir / "hamming_chart.png"
        plot_hamming_chart(hamming_distances, chart_path, title=f"Hamming — {self._task.task_id}")

        return builder.finalize(final_score=None, success=False)
