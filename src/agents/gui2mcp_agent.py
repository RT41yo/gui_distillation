"""
Gui2MCPAgent — top-level agent entry point.

Responsibilities:
  - App/task selection from registries
  - Reset policy (close → relaunch between episodes)
  - Wiring all components together
  - Running EpisodeController
  - Evaluation
  - DART export
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.agents.episode_controller import EpisodeController
from src.agents.planner import Planner
from src.domain.app_registry import AppRegistry
from src.domain.models import AppConfig, EpisodeRecord, TaskConfig
from src.domain.task_registry import TaskRegistry
from src.evaluation.base_evaluator import BaseEvaluator
from src.evaluation.calc_evaluator import CalcEvaluator
from src.evaluation.gedit_evaluator import GeditEvaluator
from src.evaluation.writer_evaluator import WriterEvaluator
from src.executor.action_executor import ActionExecutor
from src.executor.pyautogui_adapter import PyAutoGUIAdapter
from src.exporters.dart_exporter import DartExporter
from src.exporters.summary_exporter import SummaryExporter
from src.mcp_servers.tools.a11y_tool import FindElementA11YTool, GetA11YTreeTool
from src.mcp_servers.tools.export_tool import ExportDartEpisodeTool, ExportDartEpisodeInput, ExportDartSummaryTool, ExportDartSummaryInput
from src.mcp_servers.tools.evaluation_tool import EvaluateEpisodeTool, EvaluateEpisodeInput
from src.mcp_servers.tools.vision_tool import FindElementVLMTool, TakeScreenshotTool
from src.perception.a11y_service import A11YService
from src.perception.locator_service import VLMLocator
from src.perception.screenshot_service import ScreenshotService
from src.storage.artifact_store import ArtifactStore
from src.teachers.openai_client import OpenAIAnnotatorClient

logger = logging.getLogger(__name__)


class Gui2MCPAgent:
    """
    A11Y-first GUI Trajectory Agent with DART-like export.

    Usage:
        agent = Gui2MCPAgent(config)
        episode = agent.run_episode(app_id="calc", task_id="calc_001")
    """

    def __init__(
        self,
        base_output_dir: Path,
        dart_root: Path,
        display: str = ":99",
        settings_path: str = "config/settings.yaml",
        planner_config: str = "config/llm/planner_gpt-5.4-mini.yaml",
        locator_config: str = "config/llm/locator_gpt-5.4-mini.yaml",
        app_basket: str = "config/app_basket.yaml",
        task_basket: str = "config/task_basket.yaml",
        planner_prompt: str = "config/prompts/planner_task_v1.md",
        locator_prompt: str = "config/prompts/locator_vlm_v1.md",
        max_steps: int = 20,
        startup_wait: float = 3.0,
        screen_width: int = 1280,
        screen_height: int = 1024,
    ) -> None:
        self._base_output_dir = base_output_dir
        self._dart_root = dart_root
        self._display = display
        self._max_steps = max_steps
        self._startup_wait = startup_wait
        self._screen_width = screen_width
        self._screen_height = screen_height

        self._app_registry = AppRegistry(app_basket)
        self._task_registry = TaskRegistry(task_basket)

        # Shared adapter (reused across episodes; app is relaunched each time)
        self._adapter = PyAutoGUIAdapter(display=display)

        # LLM clients
        self._planner_client = OpenAIAnnotatorClient(
            settings_path=settings_path,
            teacher_config_path=planner_config,
        )
        self._locator_client = OpenAIAnnotatorClient(
            settings_path=settings_path,
            teacher_config_path=locator_config,
        )

        self._planner_prompt_path = Path(planner_prompt)
        self._locator_prompt_path = Path(locator_prompt)

        self._dart_exporter = DartExporter()
        self._summary_exporter = SummaryExporter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_episode(
        self,
        app_id: str,
        task_id: Optional[str] = None,
    ) -> EpisodeRecord:
        """
        Run one full episode (select task → reset → loop → evaluate → export).

        Returns the finalized EpisodeRecord with score.
        """
        app = self._app_registry.get(app_id)
        if task_id:
            task = self._task_registry.get(app_id, task_id)
        else:
            task = self._task_registry.select_random(app_id)

        logger.info("Starting episode: app=%s task=%s", app.app_id, task.task_id)

        # Reset policy
        self._reset(app)

        # Wire up all components for this episode
        a11y_service = A11YService(app.a11y_app_name)
        screenshot_service = ScreenshotService(display=self._display)
        vlm_locator = VLMLocator(self._locator_client, self._locator_prompt_path)

        screenshot_tool = TakeScreenshotTool(screenshot_service)
        a11y_tree_tool = GetA11YTreeTool(a11y_service)
        find_a11y_tool = FindElementA11YTool(a11y_service)
        find_vlm_tool = FindElementVLMTool(vlm_locator)

        executor = ActionExecutor(self._adapter)
        planner = Planner(self._planner_client, self._planner_prompt_path)

        from src.storage.episode_record import EpisodeRecordBuilder
        builder_probe = EpisodeRecordBuilder(app, task)
        episode_uuid = builder_probe.episode_uuid
        store = ArtifactStore(self._base_output_dir, episode_uuid)

        controller = EpisodeController(
            app=app,
            task=task,
            planner=planner,
            screenshot_tool=screenshot_tool,
            a11y_tree_tool=a11y_tree_tool,
            find_a11y_tool=find_a11y_tool,
            find_vlm_tool=find_vlm_tool,
            executor=executor,
            artifact_store=store,
            max_steps=self._max_steps,
            screen_width=self._screen_width,
            screen_height=self._screen_height,
        )

        episode = controller.run()

        # Evaluate
        evaluator = self._build_evaluator(app, task, store.episode_dir)
        eval_result = EvaluateEpisodeTool(evaluator).run(EvaluateEpisodeInput(episode=episode))
        episode = episode.model_copy(update={
            "final_score": eval_result.score,
            "success": eval_result.success,
            "evaluator_output": eval_result.details,
        })

        # Persist full episode record
        store.write_episode(episode.model_dump())

        # DART export
        ExportDartEpisodeTool(self._dart_exporter).run(
            ExportDartEpisodeInput(
                episode=episode,
                dart_root=self._dart_root,
                internal_episode_dir=store.episode_dir,
            )
        )
        ExportDartSummaryTool(self._summary_exporter).run(
            ExportDartSummaryInput(dart_root=self._dart_root)
        )

        logger.info(
            "Episode complete: app=%s task=%s score=%.2f success=%s",
            app.app_id, task.task_id, eval_result.score, eval_result.success,
        )
        return episode

    # ------------------------------------------------------------------
    # Reset policy
    # ------------------------------------------------------------------

    def _reset(self, app: AppConfig) -> None:
        """Close the app (if running) and relaunch it to a clean state."""
        logger.info("Reset: closing %s", app.app_id)
        try:
            self._adapter.close()
        except Exception as exc:
            logger.debug("Close during reset: %s", exc)

        logger.info("Reset: launching %s (%s)", app.app_id, app.launcher)
        self._adapter.launch(app.launcher, startup_wait=self._startup_wait)

    # ------------------------------------------------------------------
    # Evaluator factory (OCP: add new evaluators here without touching core)
    # ------------------------------------------------------------------

    def _build_evaluator(
        self, app: AppConfig, task: TaskConfig, episode_dir: Path
    ) -> BaseEvaluator:
        if app.app_id == "calc":
            # Extract expected value from evaluator field e.g. "display_equals_42"
            expected = task.evaluator.replace("display_equals_", "")
            return CalcEvaluator(expected_value=expected, episode_dir=episode_dir)
        if app.app_id == "writer":
            expected = task.expected_text or ""
            return WriterEvaluator(expected_text=expected, episode_dir=episode_dir)
        if app.app_id == "gedit":
            expected = task.expected_text or ""
            return GeditEvaluator(expected_text=expected, episode_dir=episode_dir)
        raise ValueError(f"No evaluator registered for app_id='{app.app_id}'")
