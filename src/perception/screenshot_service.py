"""
Screenshot service — thin wrapper around pyautogui screenshot capture.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pyautogui

logger = logging.getLogger(__name__)


class ScreenshotService:
    """Captures screenshots and saves them to disk."""

    def __init__(self, display: str = ":99") -> None:
        self._display = display
        os.environ["DISPLAY"] = display

    def capture(self, output_path: Path) -> Path:
        """
        Take a screenshot and save to output_path (PNG).

        Returns the path to the saved file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = pyautogui.screenshot()
        img.save(output_path, format="PNG")
        logger.debug("Screenshot saved → %s", output_path)
        return output_path
