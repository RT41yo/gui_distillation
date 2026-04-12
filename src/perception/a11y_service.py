"""
A11Y service — wraps A11YCapture for the gui2mcp agent.

Provides per-step tree capture, element search, and bbox extraction.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

from src.core.a11y_capture import A11YCapture

logger = logging.getLogger(__name__)

# [x, y, w, h] in pixels
A11YBBox = Tuple[int, int, int, int]


class A11YService:
    """
    Captures A11Y trees and resolves element locations.

    Uses A11YCapture under the hood; exposes a simpler interface
    tailored to per-step agent use.
    """

    def __init__(self, a11y_app_name: str, timeout: float = 8.0) -> None:
        self._app_name = a11y_app_name
        self._timeout = timeout
        self._capture = A11YCapture()

    def capture(self, output_dir: Path, step_id: int) -> Tuple[Path, Path]:
        """
        Capture A11Y tree for the current step.

        Returns (xml_path, txt_path).
        """
        suffix = f"step_{step_id:04d}"
        xml_path = output_dir / f"a11y_{suffix}.xml"
        txt_path = output_dir / f"a11y_{suffix}.txt"

        self._capture.capture_to_xml(self._app_name, xml_path, self._timeout)
        self._capture.parse_xml_to_txt(xml_path, txt_path)

        logger.debug("A11Y captured → xml=%s, txt=%s", xml_path, txt_path)
        return xml_path, txt_path

    def find_element(self, xml_path: Path, query: str) -> Optional[A11YBBox]:
        """
        Find element by name/query in the captured A11Y XML.

        Returns (x, y, w, h) in absolute pixels, or None if not found.
        """
        result = self._capture.find_button_by_name(xml_path, query)
        if result is None:
            logger.warning("A11Y: element '%s' not found in %s", query, xml_path)
        return result

    def read_txt(self, txt_path: Path) -> str:
        """Return the text content of the A11Y TXT file (for planner prompt)."""
        if not txt_path.exists():
            return ""
        return txt_path.read_text(encoding="utf-8")
