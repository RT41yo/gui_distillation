"""
Artifact store — writes files to disk for a given episode/step.

Responsible for directory layout and file I/O only; no business logic.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ArtifactStore:
    """
    Manages the on-disk layout for a single episode run.

    Layout:
        <base_dir>/<episode_uuid>/
            step_0000.png
            a11y_step_0000.xml
            a11y_step_0000.txt
            steps/
                step_0000.json   ← StepRecord JSON
            episode.json         ← EpisodeRecord JSON (written at end)
    """

    def __init__(self, base_dir: Path, episode_uuid: str) -> None:
        self.episode_dir = base_dir / episode_uuid
        self.steps_dir = self.episode_dir / "steps"
        self.episode_dir.mkdir(parents=True, exist_ok=True)
        self.steps_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("ArtifactStore ready at %s", self.episode_dir)

    def screenshot_path(self, step_id: int) -> Path:
        return self.episode_dir / f"step_{step_id:04d}.png"

    def a11y_xml_path(self, step_id: int) -> Path:
        return self.episode_dir / f"a11y_step_{step_id:04d}.xml"

    def a11y_txt_path(self, step_id: int) -> Path:
        return self.episode_dir / f"a11y_step_{step_id:04d}.txt"

    def write_step(self, step_id: int, data: Dict[str, Any]) -> Path:
        path = self.steps_dir / f"step_{step_id:04d}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_episode(self, data: Dict[str, Any]) -> Path:
        path = self.episode_dir / "episode.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Episode record written → %s", path)
        return path

    def copy_screenshot(self, src: Path, step_id: int) -> Path:
        dst = self.screenshot_path(step_id)
        shutil.copy2(src, dst)
        return dst
