"""
LibreOffice Writer evaluator.

Checks whether the expected text appears in the last A11Y tree snapshot.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from src.domain.models import EpisodeRecord
from src.evaluation.base_evaluator import BaseEvaluator, EvaluationResult

logger = logging.getLogger(__name__)


def _find_text_in_xml(xml_path: Path, expected: str) -> bool:
    """Return True if expected text appears in any A11Y element name/description."""
    if not xml_path.exists():
        return False
    try:
        tree = ET.parse(xml_path)
        for elem in tree.getroot().iter("element"):
            name = elem.get("name") or ""
            desc = elem.get("description") or ""
            if expected in name or expected in desc:
                return True
    except Exception as exc:
        logger.warning("Failed to parse A11Y XML %s: %s", xml_path, exc)
    return False


class WriterEvaluator(BaseEvaluator):
    """
    Evaluates LibreOffice Writer tasks.

    Checks for expected_text presence in the last captured A11Y XML.
    """

    def __init__(self, expected_text: str, episode_dir: Path) -> None:
        self._expected = expected_text
        self._episode_dir = episode_dir

    def evaluate(self, episode: EpisodeRecord) -> EvaluationResult:
        last_xml: Optional[Path] = None
        for step in reversed(episode.steps):
            if step.a11y_tree_file:
                candidate = self._episode_dir / step.a11y_tree_file
                if candidate.exists():
                    last_xml = candidate
                    break

        if last_xml is None:
            return EvaluationResult(score=0.0, success=False, details={"reason": "no_a11y_xml"})

        found = _find_text_in_xml(last_xml, self._expected)
        score = 1.0 if found else 0.0
        return EvaluationResult(
            score=score,
            success=found,
            details={"expected_text": self._expected, "found": found, "xml": str(last_xml)},
        )
