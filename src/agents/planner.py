"""
Planner — calls the LLM to decide the next GUI action.

Responsibilities:
  - Build the planner prompt from template + context
  - Call OpenAI via OpenAIAnnotatorClient
  - Parse the raw response into PlannerResponse
  - Log thought and action for debugging

Does NOT execute GUI actions or interact with pyautogui.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from src.domain.models import ActionType, PlannerResponse
from src.teachers.openai_client import OpenAIAnnotatorClient
from src.teachers.json_parser import RobustJSONParser

_json_parser = RobustJSONParser()

logger = logging.getLogger(__name__)


class Planner:
    """
    Wraps the LLM call for action planning.

    Takes a screenshot + A11Y element list and returns a PlannerResponse.
    """

    def __init__(self, client: OpenAIAnnotatorClient, prompt_path: Path) -> None:
        self._client = client
        self._prompt_template = (
            prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        )

    def plan(
        self,
        task_instruction: str,
        app_display_name: str,
        step_num: int,
        max_steps: int,
        a11y_elements: str,
        action_history: List[str],
        screenshot_path: Optional[Path],
    ) -> PlannerResponse:
        """
        Ask the LLM for the next action.

        Returns a PlannerResponse with thought, target_query, action_type, done.
        """
        history_text = "\n".join(action_history[-10:]) if action_history else "None"

        prompt = (
            self._prompt_template
            .replace("{task_instruction}", task_instruction)
            .replace("{app_display_name}", app_display_name)
            .replace("{step_num}", str(step_num))
            .replace("{max_steps}", str(max_steps))
            .replace("{a11y_elements}", a11y_elements or "(empty)")
            .replace("{action_history}", history_text)
        )

        image_paths = [screenshot_path] if screenshot_path and screenshot_path.exists() else []

        try:
            raw = self._client.infer(
                prompt_text=prompt,
                image_paths=image_paths,
                prefer_json=True,
            )
            return self._parse(raw.text)
        except Exception as exc:
            logger.error("Planner LLM call failed: %s", exc)
            return PlannerResponse(
                thought=f"LLM error: {exc}",
                target_query="",
                action_type=ActionType.WAIT,
                done=False,
                raw_response=str(exc),
            )

    def _parse(self, text: str) -> PlannerResponse:
        """Parse JSON response into PlannerResponse."""
        result = _json_parser.parse(text)
        parsed = result.data if result.ok else None
        if parsed is None:
            parsed = {}

        if not isinstance(parsed, dict):
            parsed = {}

        thought = str(parsed.get("thought", ""))
        target_query = str(parsed.get("target_query", ""))
        done = bool(parsed.get("done", False))

        action_type_raw = str(parsed.get("action_type", "wait")).lower()
        try:
            action_type = ActionType(action_type_raw)
        except ValueError:
            logger.warning("Unknown action_type '%s' — defaulting to wait", action_type_raw)
            action_type = ActionType.WAIT

        if done:
            action_type = ActionType.DONE

        logger.info("[Planner] thought=%s | action=%s | target=%s | done=%s",
                    thought[:80], action_type.value, target_query, done)

        return PlannerResponse(
            thought=thought,
            target_query=target_query,
            action_type=action_type,
            text=parsed.get("text"),
            keys=parsed.get("keys"),
            done=done,
            raw_response=text,
        )
