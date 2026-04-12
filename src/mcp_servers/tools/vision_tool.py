"""
MCP-style vision tools: screenshot capture and VLM-based element location.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.domain.models import LocatorResult
from src.perception.screenshot_service import ScreenshotService
from src.perception.locator_service import VLMLocator


@dataclass
class TakeScreenshotInput:
    output_path: Path


@dataclass
class TakeScreenshotOutput:
    path: Path


class TakeScreenshotTool:
    """Capture a screenshot and save to disk."""

    def __init__(self, screenshot_service: ScreenshotService) -> None:
        self._service = screenshot_service

    def run(self, inp: TakeScreenshotInput) -> TakeScreenshotOutput:
        path = self._service.capture(inp.output_path)
        return TakeScreenshotOutput(path=path)


# ---------------------------------------------------------------------------

@dataclass
class FindElementVLMInput:
    screenshot_path: Path
    query: str
    screen_width: int = 1280
    screen_height: int = 1024
    app_display_name: str = ""


class FindElementVLMTool:
    """Ask a VLM to locate an element in a screenshot."""

    def __init__(self, vlm_locator: VLMLocator) -> None:
        self._locator = vlm_locator

    def run(self, inp: FindElementVLMInput) -> LocatorResult:
        return self._locator.locate(
            query=inp.query,
            xml_path=None,
            screenshot_path=inp.screenshot_path,
            screen_width=inp.screen_width,
            screen_height=inp.screen_height,
            app_display_name=inp.app_display_name,
        )
