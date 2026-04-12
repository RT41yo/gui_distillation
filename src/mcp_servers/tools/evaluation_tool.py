"""
MCP-style evaluation tool.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from src.domain.models import EpisodeRecord
from src.evaluation.base_evaluator import BaseEvaluator


@dataclass
class EvaluateEpisodeInput:
    episode: EpisodeRecord


@dataclass
class EvaluateEpisodeOutput:
    score: float
    success: bool
    details: Dict[str, Any]


class EvaluateEpisodeTool:
    """Run the app-specific evaluator on a completed episode."""

    def __init__(self, evaluator: BaseEvaluator) -> None:
        self._evaluator = evaluator

    def run(self, inp: EvaluateEpisodeInput) -> EvaluateEpisodeOutput:
        result = self._evaluator.evaluate(inp.episode)
        return EvaluateEpisodeOutput(
            score=result.score,
            success=result.success,
            details=result.details,
        )
