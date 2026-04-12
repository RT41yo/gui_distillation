"""
Action executor — translates PlannerResponse + LocatorResult into
a concrete ExecutorAction and dispatches it via PyAutoGUIAdapter.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.domain.models import ActionType, ExecutorAction, LocatorResult, PlannerResponse
from src.executor.pyautogui_adapter import PyAutoGUIAdapter

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Receives a planner decision + locator result and executes the GUI action.

    Does not make any planning decisions — only dispatches.
    """

    def __init__(self, adapter: PyAutoGUIAdapter) -> None:
        self._adapter = adapter

    def execute(
        self,
        planner: PlannerResponse,
        locator: Optional[LocatorResult],
    ) -> ExecutorAction:
        """
        Build and execute an ExecutorAction.

        Returns the ExecutorAction that was executed (for recording).
        """
        action_type = planner.action_type

        if action_type == ActionType.DONE:
            logger.info("Action: DONE — no GUI interaction")
            return ExecutorAction(tool="done")

        if action_type == ActionType.WAIT:
            duration = 1.0
            self._adapter.wait(duration)
            return ExecutorAction(tool="wait", duration=duration)

        if action_type == ActionType.HOTKEY:
            keys = planner.keys or []
            if not keys:
                logger.warning("hotkey action with no keys — skipping")
                return ExecutorAction(tool="hotkey", keys=[])
            self._adapter.hotkey(keys)
            return ExecutorAction(tool="hotkey", keys=keys)

        if action_type == ActionType.TYPE_TEXT:
            text = planner.text or ""
            self._adapter.type_text(text)
            return ExecutorAction(tool="type_text", text=text)

        # For click and scroll we need coordinates
        x, y = self._resolve_coords(locator)

        if action_type == ActionType.CLICK:
            self._adapter.click(x, y)
            return ExecutorAction(tool="click", x=x, y=y, button="left")

        if action_type == ActionType.SCROLL:
            self._adapter.scroll(x, y)
            return ExecutorAction(tool="scroll", x=x, y=y)

        logger.warning("Unknown action_type '%s' — skipping", action_type)
        return ExecutorAction(tool="noop")

    def _resolve_coords(self, locator: Optional[LocatorResult]) -> tuple[float, float]:
        """Extract center coordinates from locator result."""
        if locator and locator.found and locator.center:
            return locator.center[0], locator.center[1]
        raise ValueError(
            "Cannot execute positional action: locator did not return coordinates. "
            f"Locator: {locator}"
        )
