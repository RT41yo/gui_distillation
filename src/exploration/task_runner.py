"""
Task-driven online agent loop for GUI automation.

The agent receives a high-level natural-language task, then at each step:
  1. Takes a screenshot of the current UI state.
  2. Sends the screenshot + task context + history to an LLM.
  3. Parses the LLM response to get the next button to click.
  4. Executes the action and records all artifacts via GUIAutomation.run_step().
  5. Repeats until the LLM signals task_complete or max_steps is reached.

Usage:
    python -m src.exploration.task_runner \\
        --task "add 3 and 5, then subtract 2" \\
        --max-steps 20 \\
        --settings config/settings.yaml \\
        --app-config config/apps/calculator.yaml \\
        --teacher-config config/teachers/openai_gpt.yaml \\
        --output data/exploration/task_runs/run_001
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.automation import GUIAutomation
from src.core.exceptions import ActionExecutionError
from src.teachers.json_parser import RobustJSONParser
from src.teachers.openai_client import OpenAIAnnotatorClient
from src.teachers.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

JsonDict = Dict[str, Any]

_DONE_SENTINEL = "__done__"


class TaskRunner:
    """
    Online LLM-driven agent that executes a natural-language task
    on a running GUI application step by step.
    """

    def __init__(
        self,
        automation: GUIAutomation,
        llm_client: OpenAIAnnotatorClient,
        prompt_template: str,
        max_steps: int = 20,
    ) -> None:
        self.automation = automation
        self.llm_client = llm_client
        self.prompt_template = prompt_template
        self.max_steps = max_steps
        self._parser = RobustJSONParser()
        self._buttons: Dict[str, List[int]] = dict(
            automation.app_config.get("buttons", {})
        )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _button_list_text(self) -> str:
        # List only IDs — coordinates are looked up internally and must not appear
        # in the prompt to avoid the model confusing coordinate values with IDs.
        return ", ".join(self._buttons.keys())

    def _history_text(self, history: List[JsonDict]) -> str:
        if not history:
            return "  (no actions yet)"
        lines = []
        for i, entry in enumerate(history):
            if entry.get("error"):
                lines.append(f"  Step {i}: tried '{entry['button_id']}' — ERROR: {entry['error']}")
            else:
                lines.append(f"  Step {i}: clicked {entry['button_id']} — {entry['rationale']}")
        return "\n".join(lines)

    def _build_prompt(self, task: str, history: List[JsonDict]) -> str:
        return self.prompt_template.format(
            task=task,
            button_list=self._button_list_text(),
            history=self._history_text(history),
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self, task: str) -> JsonDict:
        """
        Execute the task using the running application managed by self.automation.
        The caller is responsible for launching / closing the app (use GUIAutomation
        as a context manager or call launch_app() / close_app() explicitly).

        Returns a report dict saved to {output_dir}/task_run_report.json.
        """
        history: List[JsonDict] = []
        step_reports: List[JsonDict] = []
        task_complete = False

        for step_id in range(self.max_steps):
            logger.info("--- Task step %d ---", step_id)

            # 1. Screenshot for LLM (temporary file, cleaned up after run_step)
            tmp_screenshot = self.automation.output_dir / f"_llm_input_{step_id:04d}.png"
            self.automation.take_screenshot(tmp_screenshot)

            # 2. Build prompt and call LLM
            prompt = self._build_prompt(task, history)
            t0 = time.perf_counter()
            raw = self.llm_client.infer(prompt, image_paths=[tmp_screenshot])
            latency_s = time.perf_counter() - t0
            logger.debug("LLM response (%.2fs): %s", latency_s, raw.text[:200])

            # 3. Parse LLM response
            parse_result = self._parser.parse(raw.text)
            if not parse_result.ok or not isinstance(parse_result.data, dict):
                logger.warning("Step %d: LLM parse failed (%s): %s", step_id, parse_result.mode, parse_result.error)
                step_reports.append({
                    "step_id": step_id,
                    "error": f"parse_failed: {parse_result.error}",
                    "raw_response": raw.text[:500],
                    "latency_s": latency_s,
                    "usage": raw.usage,
                })
                tmp_screenshot.unlink(missing_ok=True)
                continue

            data: JsonDict = parse_result.data  # type: ignore[assignment]
            button_id: str = str(data.get("button_id", "")).strip()
            rationale: str = str(data.get("rationale", ""))
            task_complete = bool(data.get("task_complete", False))

            report_entry: JsonDict = {
                "step_id": step_id,
                "button_id": button_id,
                "rationale": rationale,
                "task_complete": task_complete,
                "parse_mode": parse_result.mode,
                "latency_s": round(latency_s, 3),
                "usage": raw.usage,
            }

            # 4. Check for completion
            if task_complete or button_id == _DONE_SENTINEL:
                logger.info("Task complete at step %d: %s", step_id, rationale)
                step_reports.append(report_entry)
                tmp_screenshot.unlink(missing_ok=True)
                break

            # 5. Validate button_id
            coords = self.automation.get_button_coordinates(button_id)
            if coords is None:
                error_msg = f"'{button_id}' is not a valid button ID. Use only IDs from the list."
                logger.warning("Step %d: unknown button_id '%s', feeding error back to LLM", step_id, button_id)
                report_entry["error"] = f"unknown_button_id: {button_id}"
                step_reports.append(report_entry)
                tmp_screenshot.unlink(missing_ok=True)
                history.append({"button_id": button_id, "rationale": rationale, "error": error_msg})
                continue

            # 6. Build action config with button_id and rationale stored for traceability
            action_config: JsonDict = {
                "action_type": "click",
                "coordinates": list(coords),
                "parameters": {"button": "left", "clicks": 1},
                "button_id": button_id,
                "rationale": rationale,
            }

            # 7. Execute step — run_step takes its own before.png right before the action
            try:
                self.automation.run_step(step_id, action_config)
            except ActionExecutionError as exc:
                logger.error("Step %d: action execution failed: %s", step_id, exc)
                report_entry["error"] = f"action_failed: {exc}"
                step_reports.append(report_entry)
                tmp_screenshot.unlink(missing_ok=True)
                continue

            # 8. Cleanup temp screenshot (run_step saved its own before.png)
            tmp_screenshot.unlink(missing_ok=True)

            history.append({"button_id": button_id, "rationale": rationale})
            step_reports.append(report_entry)
            logger.info("Step %d: %s — %s", step_id, button_id, rationale)

        report: JsonDict = {
            "task": task,
            "total_steps": len(step_reports),
            "task_complete": task_complete,
            "steps": step_reports,
        }

        report_path = self.automation.output_dir / "task_run_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Task run report saved to %s", report_path)

        return report


# =========================================================
# CLI
# =========================================================

def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Task-driven online LLM agent for GUI automation"
    )
    parser.add_argument("--task", required=True, help="Natural-language task to execute")
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum number of steps (default: 20)")
    parser.add_argument("--settings", default="config/settings.yaml", help="Path to settings.yaml")
    parser.add_argument("--app-config", default="config/apps/calculator.yaml", help="Path to app config YAML")
    parser.add_argument("--teacher-config", default="config/teachers/openai_gpt.yaml", help="Path to teacher config YAML")
    parser.add_argument("--output", required=True, help="Output directory for step artifacts")
    parser.add_argument("--app", default="gnome-calculator", help="Application binary name")
    parser.add_argument("--prompt", default="config/prompts/action_task_v1.md", help="Path to prompt template")
    parser.add_argument("--display", default=None, help="X11 display (overrides settings)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        logger.error("Prompt template not found: %s", prompt_path)
        return 1

    prompt_template = PromptLoader(prompt_path.parent).load(prompt_path.name)

    automation = GUIAutomation(
        app_name=args.app,
        output_dir=args.output,
        settings_path=args.settings,
        app_config_path=args.app_config,
        display=args.display,
    )

    llm_client = OpenAIAnnotatorClient(
        settings_path=args.settings,
        teacher_config_path=args.teacher_config,
    )

    runner = TaskRunner(
        automation=automation,
        llm_client=llm_client,
        prompt_template=prompt_template,
        max_steps=args.max_steps,
    )

    with automation:
        report = runner.run(args.task)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
