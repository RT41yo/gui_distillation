"""
Calculator evaluator.

Checks the GNOME Calculator display value via the A11Y tree
of the last captured step.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from src.domain.models import EpisodeRecord
from src.evaluation.base_evaluator import BaseEvaluator, EvaluationResult

logger = logging.getLogger(__name__)

# A11Y role names that represent the calculator display
_DISPLAY_ROLES = {"label", "text", "entry"}


def _read_display_from_xml(xml_path: Path) -> Optional[str]:
    """Extract the calculator display value from an A11Y XML snapshot.

    GNOME Calculator keeps a history of results in the A11Y tree as labels,
    so we collect ALL pure numeric labels (no operators, no unit suffixes)
    and return the LAST one — which corresponds to the most recent result.
    Hex values (e.g. 'ff') and plain integers/floats are both accepted.
    """
    if not xml_path.exists():
        return None
    try:
        tree = ET.parse(xml_path)
        candidates: list[str] = []
        for elem in tree.getroot().iter("element"):
            role = (elem.get("role") or "").lower()
            name = (elem.get("name") or "").strip()
            if role not in _DISPLAY_ROLES or not name:
                continue
            # Accept pure numeric (int/float) or pure hex string
            try:
                float(name.replace(",", "."))
                candidates.append(name)
                continue
            except ValueError:
                pass
            if all(c in "0123456789abcdefABCDEF" for c in name) and name:
                candidates.append(name)
        return candidates[-1] if candidates else None
    except Exception as exc:
        logger.warning("Failed to parse A11Y XML %s: %s", xml_path, exc)
    return None


class CalcEvaluator(BaseEvaluator):
    """
    Evaluates GNOME Calculator tasks by reading the display via A11Y XML.

    Expects task_config.expected_text to hold the expected numeric result
    as a string (e.g. "42").
    """

    def __init__(self, expected_value: str, episode_dir: Path) -> None:
        self._expected = expected_value.strip()
        self._episode_dir = episode_dir

    def evaluate(self, episode: EpisodeRecord) -> EvaluationResult:
        # Find the last A11Y XML captured in the episode
        last_xml: Optional[Path] = None
        for step in reversed(episode.steps):
            if step.a11y_tree_file:
                candidate = self._episode_dir / step.a11y_tree_file
                if candidate.exists():
                    last_xml = candidate
                    break

        if last_xml is None:
            logger.warning("CalcEvaluator: no A11Y XML found")
            return EvaluationResult(score=0.0, success=False, details={"reason": "no_a11y_xml"})

        display = _read_display_from_xml(last_xml)
        if display is None:
            logger.warning("CalcEvaluator: could not read display from %s", last_xml)
            return EvaluationResult(score=0.0, success=False, details={"reason": "display_not_found"})

        # Normalize: strip trailing zeros for float comparison
        try:
            actual = str(float(display))
            expected = str(float(self._expected))
            matched = actual == expected
        except ValueError:
            matched = display.strip() == self._expected

        score = 1.0 if matched else 0.0
        return EvaluationResult(
            score=score,
            success=matched,
            details={"display": display, "expected": self._expected, "xml": str(last_xml)},
        )
