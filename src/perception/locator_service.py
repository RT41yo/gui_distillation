"""
Locator service — abstracts element location from multiple backends.

Policy:
  - Primary: A11YLocator (always used)
  - Secondary: VLMLocator (always called in parallel for IoU metric)
  - Fallback: VLMLocator coordinates used only if A11Y returns nothing
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.domain.models import LocatorResult
from src.perception.a11y_service import A11YService
from src.teachers.openai_client import OpenAIAnnotatorClient
from src.teachers.json_parser import RobustJSONParser

_json_parser = RobustJSONParser()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseLocator(ABC):
    """Interface all locators must implement (LSP / ISP)."""

    @abstractmethod
    def locate(self, query: str, xml_path: Optional[Path], screenshot_path: Optional[Path]) -> LocatorResult:
        """Find element matching query. Returns LocatorResult (found or not)."""


# ---------------------------------------------------------------------------
# A11Y locator
# ---------------------------------------------------------------------------

class A11YLocator(BaseLocator):
    """Locates elements via the AT-SPI accessibility tree."""

    def __init__(self, a11y_service: A11YService) -> None:
        self._a11y = a11y_service

    def locate(self, query: str, xml_path: Optional[Path], screenshot_path: Optional[Path]) -> LocatorResult:
        if xml_path is None or not xml_path.exists():
            return LocatorResult(source="a11y", found=False)

        raw = self._a11y.find_element(xml_path, query)
        if raw is None:
            return LocatorResult(source="a11y", found=False, element_name=query)

        x, y, w, h = raw
        cx = x + w / 2.0
        cy = y + h / 2.0
        return LocatorResult(
            source="a11y",
            found=True,
            element_name=query,
            bbox=[float(x), float(y), float(w), float(h)],
            center=(cx, cy),
            confidence=1.0,
        )


# ---------------------------------------------------------------------------
# VLM locator
# ---------------------------------------------------------------------------

class VLMLocator(BaseLocator):
    """Locates elements by asking a vision-language model."""

    def __init__(self, client: OpenAIAnnotatorClient, prompt_path: Path) -> None:
        self._client = client
        self._prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

    def locate(self, query: str, xml_path: Optional[Path], screenshot_path: Optional[Path]) -> LocatorResult:
        if screenshot_path is None or not screenshot_path.exists():
            return LocatorResult(source="vlm", found=False)

        prompt = self._prompt_template.replace("{target_query}", query)

        try:
            raw_resp = self._client.infer(
                prompt_text=prompt,
                image_paths=[screenshot_path],
                prefer_json=True,
            )
            result = _json_parser.parse(raw_resp.text)
            parsed = result.data if result.ok else None
            if parsed is None:
                parsed = json.loads(raw_resp.text)

            found = bool(parsed.get("found", False))
            bbox = parsed.get("bbox")   # [x1, y1, x2, y2]
            center_raw = parsed.get("center")
            confidence = float(parsed.get("confidence", 0.0))

            if not found or bbox is None:
                return LocatorResult(source="vlm", found=False, raw=parsed)

            # Convert [x1,y1,x2,y2] to [x, y, w, h] for consistency with A11Y
            x1, y1, x2, y2 = bbox
            w = x2 - x1
            h = y2 - y1
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            center = (float(center_raw[0]), float(center_raw[1])) if center_raw else (cx, cy)

            return LocatorResult(
                source="vlm",
                found=True,
                element_name=parsed.get("element_description", query),
                bbox=[float(x1), float(y1), float(w), float(h)],
                center=center,
                confidence=confidence,
                raw=parsed,
            )

        except Exception as exc:
            logger.warning("VLM locator failed for '%s': %s", query, exc)
            return LocatorResult(source="vlm", found=False, raw={"error": str(exc)})


# ---------------------------------------------------------------------------
# Composite locator (policy: A11Y primary, VLM parallel for IoU)
# ---------------------------------------------------------------------------

class CompositeLocator:
    """
    Runs A11Y and VLM locators.

    Always returns both results:
      - primary_result: from A11Y (or VLM if A11Y failed)
      - vlm_result: from VLM (always, for IoU computation)
    """

    def __init__(self, a11y_locator: A11YLocator, vlm_locator: VLMLocator) -> None:
        self._a11y = a11y_locator
        self._vlm = vlm_locator

    def locate(
        self,
        query: str,
        xml_path: Optional[Path],
        screenshot_path: Optional[Path],
    ) -> tuple[LocatorResult, LocatorResult]:
        """
        Returns (primary_result, vlm_result).

        primary_result: A11Y if found, else VLM fallback.
        vlm_result: always the raw VLM result (for IoU).
        """
        a11y_result = self._a11y.locate(query, xml_path, screenshot_path)
        vlm_result = self._vlm.locate(query, xml_path, screenshot_path)

        if a11y_result.found:
            primary = a11y_result
        else:
            logger.info("A11Y miss for '%s' — falling back to VLM", query)
            primary = vlm_result

        return primary, vlm_result
