"""
Episode record builder — accumulates steps and finalizes the episode.
"""
from __future__ import annotations

import uuid
from collections import Counter
from typing import Any, Dict, List, Optional

from src.domain.models import AppConfig, EpisodeRecord, StepRecord, TaskConfig
from src.storage.step_record import make_timestamp


class EpisodeRecordBuilder:
    """
    Accumulates StepRecords during an episode and builds the final EpisodeRecord.
    """

    def __init__(self, app: AppConfig, task: TaskConfig) -> None:
        self._app = app
        self._task = task
        self._episode_uuid = str(uuid.uuid4())
        self._steps: List[StepRecord] = []
        self._started_at = make_timestamp()

    @property
    def episode_uuid(self) -> str:
        return self._episode_uuid

    def add_step(self, step: StepRecord) -> None:
        self._steps.append(step)

    def finalize(
        self,
        final_score: Optional[float],
        success: bool,
        evaluator_output: Optional[Dict[str, Any]] = None,
    ) -> EpisodeRecord:
        """Build and return the completed EpisodeRecord."""
        source_counts: Dict[str, int] = dict(
            Counter(s.locator_source for s in self._steps if s.locator_source)
        )
        return EpisodeRecord(
            episode_uuid=self._episode_uuid,
            app_id=self._app.app_id,
            app_display_name=self._app.display_name,
            task_id=self._task.task_id,
            task_instruction=self._task.instruction,
            steps=self._steps,
            final_score=final_score,
            success=success,
            evaluator_output=evaluator_output or {},
            started_at=self._started_at,
            finished_at=make_timestamp(),
            total_steps=len(self._steps),
            locator_source_counts=source_counts,
        )
