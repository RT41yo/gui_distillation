"""
Base evaluator — abstract interface all app evaluators must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict

from src.domain.models import EpisodeRecord


@dataclass
class EvaluationResult:
    score: float                            # 0.0 – 1.0 (or float)
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)


class BaseEvaluator(ABC):
    """
    Evaluates a completed episode and returns a score.

    Called once after the episode loop finishes.
    Must not interact with the GUI directly.
    """

    @abstractmethod
    def evaluate(self, episode: EpisodeRecord) -> EvaluationResult:
        """Return the evaluation result for the episode."""
