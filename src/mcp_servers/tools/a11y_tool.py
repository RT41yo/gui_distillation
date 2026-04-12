"""
MCP-style A11Y tools.

Each tool is a class with a single `run()` method (ISP).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from src.domain.models import LocatorResult
from src.perception.a11y_service import A11YService


@dataclass
class GetA11YTreeInput:
    output_dir: Path
    step_id: int


@dataclass
class GetA11YTreeOutput:
    xml_path: Path
    txt_path: Path


class GetA11YTreeTool:
    """Capture the current A11Y tree and save XML + TXT artifacts."""

    def __init__(self, a11y_service: A11YService) -> None:
        self._service = a11y_service

    def run(self, inp: GetA11YTreeInput) -> GetA11YTreeOutput:
        xml, txt = self._service.capture(inp.output_dir, inp.step_id)
        return GetA11YTreeOutput(xml_path=xml, txt_path=txt)


# ---------------------------------------------------------------------------

@dataclass
class FindElementA11YInput:
    xml_path: Path
    query: str


class FindElementA11YTool:
    """Find an element by name in the A11Y XML and return its LocatorResult."""

    def __init__(self, a11y_service: A11YService) -> None:
        self._service = a11y_service

    def run(self, inp: FindElementA11YInput) -> LocatorResult:
        raw = self._service.find_element(inp.xml_path, inp.query)
        if raw is None:
            return LocatorResult(source="a11y", found=False, element_name=inp.query)
        x, y, w, h = raw
        return LocatorResult(
            source="a11y",
            found=True,
            element_name=inp.query,
            bbox=[float(x), float(y), float(w), float(h)],
            center=(x + w / 2.0, y + h / 2.0),
            confidence=1.0,
        )
